"""Run the three Harbor Invest modules in one local simulation."""

import argparse
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from secrets import token_urlsafe
import sys
import webbrowser
from tempfile import TemporaryDirectory
from threading import Event, Thread


ROOT = Path(__file__).resolve().parent
for module in ("frontend", "middle-office", "ai"):
    sys.path.insert(0, str(ROOT / module))

from UI import create_server
from bff import DemoSessions, JsonService
from ai_mvp.assistant import Assistant
from ai_mvp.models import from_environment, remote_from_environment
from ai_mvp.profiles import ProfileStore
from ai_mvp.product_catalog import PRODUCTS, order_policies
from ai_mvp.providers import HttpMarketProvider, HttpTradingProvider, QuoteBook
from ai_mvp.server import ApiServer
from middle_office.public_market import PROVIDER_MARKETS, QUOTE_MAX_AGE, PublicMarketFeed
from middle_office.simulated_market import SIMULATED_BASES, SIMULATED_SOURCES
from middle_office.service import MiddleOffice
from middle_office.server import Server
from middle_office.validation import amount, iso


HOST = "127.0.0.1"
DEMO_POLICIES = order_policies()
DEMO_PRODUCT_RISKS = {symbol: policy["grade"] for symbol, policy in DEMO_POLICIES.items()}
DEMO_PRODUCT_REQUIREMENTS = {symbol: policy["requirements"] for symbol, policy in DEMO_POLICIES.items()}
FIXTURE_PAIRS = tuple(symbol for symbol in PRODUCTS if symbol.split("/")[0] not in SIMULATED_BASES)
FIXTURE_RATES = {"demo:HashKey": "0.001", "demo:OSL": "0.0015"}
OFFLINE_MARKETS = {**SIMULATED_SOURCES, **{source: FIXTURE_PAIRS for source in FIXTURE_RATES}}
ASSESSMENT = {
    "questionnaire_version": "1.0.0",
    "source": "questionnaire",
    "assessment": {
        "dimensions": {"FC": 62, "RA": 65, "KE": 75, "BD": 60, "OC": 55},
        "rai": 63,
        "risk_level": "C3",
        "product_cap": "R3",
    },
}


def demo_quotes():
    as_of = iso(datetime.now(timezone.utc))
    quotes = []
    tick = Decimal("0.00000001")
    for symbol in FIXTURE_PAIRS:
        product = PRODUCTS[symbol]
        mid = Decimal(str(product["demo_price"]))
        spread = max(tick, (mid * Decimal("0.0001")).quantize(tick))
        for index, (source, rate) in enumerate(FIXTURE_RATES.items()):
            price = mid + 2 * index * spread
            bid, ask = price - spread, price + spread
            quotes.append({
                "symbol": symbol, "name": product["name"], "aliases": [symbol.split("/")[0]],
                "as_of": as_of, "timestamp_source": "collected", "source": source, "price": amount(price),
                "bid": amount(bid), "ask": amount(ask), "fee_rate": rate,
                "bid_size": amount(Decimal("100000") / bid), "ask_size": amount(Decimal("100000") / ask),
            })
    return {"quotes": quotes}


def start_server(resources, server):
    resources.enter_context(server)
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
    thread.start()
    resources.callback(thread.join)
    resources.callback(server.shutdown)
    return f"http://{HOST}:{server.server_port}"


@contextmanager
def demo_stack(*, ui_port=None, ollama_model=None, enable_deepseek=False, live_market=False, data_dir=None):
    with ExitStack() as resources:
        db = Path(data_dir) if data_dir is not None else Path(resources.enter_context(
            TemporaryDirectory(prefix="harbor-invest-")
        ))
        db.mkdir(parents=True, exist_ok=True)
        operator, reader, ai_token = (token_urlsafe(24) for _ in range(3))
        sources = PROVIDER_MARKETS if live_market else OFFLINE_MARKETS
        office = MiddleOffice(db / "ledger.sqlite3", max_quote_age=QUOTE_MAX_AGE if live_market else 120,
                              public_sources=sources, public_source_pairs=sources,
                              product_risks=DEMO_PRODUCT_RISKS,
                              product_requirements=DEMO_PRODUCT_REQUIREMENTS, chart_pairs=PRODUCTS,
                              suitability_advisory=True)
        server = Server((HOST, 0), office, token=operator, read_token=reader)
        middle_url = start_server(resources, server)
        middle = JsonService("middle_office", middle_url, operator)
        reader_client = JsonService("middle_office", middle_url, reader)
        account_seed = {
            "initial_balances": {"USDT": "10000"},
            "initial_positions": [{"symbol": "BTC/USDT", "quantity": "0.1", "average_cost": "65000"}],
        }
        if not live_market:
            office.ingest_quotes(demo_quotes())
            start_demo_feed(resources, office)
        feed = server.public_feed = PublicMarketFeed(office, include_public=live_market)
        feed.start()
        resources.callback(feed.stop)
        market_url = middle_url + "/api"
        assistant = Assistant(
            ProfileStore(db / "profiles.sqlite3"), QuoteBook(),
            model=from_environment(model_name=ollama_model) if ollama_model else None,
            remote_model=remote_from_environment(enabled=True) if enable_deepseek else None,
            market_provider=HttpMarketProvider(market_url, token=reader, include_venues=True),
            trading=HttpTradingProvider(market_url, token=reader),
            quote_max_age=QUOTE_MAX_AGE if live_market else 120,
        )
        ai_url = start_server(resources, ApiServer(0, assistant, ai_token))
        ai = JsonService("ai", ai_url, ai_token, timeout=450 if ollama_model or enable_deepseek else 8)
        ui, _ = create_server(DemoSessions(ai, middle, account_seed=account_seed), port=ui_port)
        ui_url = start_server(resources, ui)
        yield middle, ai, reader_client, ui_url


def start_demo_feed(resources, office):
    # Refresh the timestamp of fixed simulated values while the offline demo is active.
    stop = Event()

    def refresh_quotes():
        while not stop.wait(30):
            office.ingest_quotes(demo_quotes())

    feed = Thread(target=refresh_quotes, daemon=True)
    feed.start()
    resources.callback(feed.join)
    resources.callback(stop.set)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, help="UI port. Defaults to the first free port from 5510 to 5529.")
    parser.add_argument("--open-browser", action="store_true", help="open the connected demo in the default browser")
    parser.add_argument("--ollama-model", help="Installed local Ollama model")
    parser.add_argument("--enable-deepseek", action="store_true", help="Opt in to the API-key model")
    parser.add_argument("--live-market", action="store_true", help="add public spot quotes for other assets")
    parser.add_argument("--data-dir", type=Path, help="reuse a directory for the simulation databases")
    args = parser.parse_args()
    try:
        with demo_stack(ui_port=args.port, ollama_model=args.ollama_model, enable_deepseek=args.enable_deepseek,
                        live_market=args.live_market, data_dir=args.data_dir) as stack:
            mode = "public market data, simulated execution" if args.live_market else "offline simulation"
            print(f"Harbor Invest ({mode}): {stack[-1]}/  (Ctrl+C to stop)", flush=True)
            if args.open_browser:
                webbrowser.open(stack[-1] + "/")
            Event().wait()
    except KeyboardInterrupt:
        pass
    except (OSError, ValueError, RuntimeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
