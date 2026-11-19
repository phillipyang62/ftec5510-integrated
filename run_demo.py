"""Run the three Harbor Invest modules in one local simulation."""

import argparse
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from secrets import token_urlsafe
import sys
from tempfile import TemporaryDirectory
from threading import Event, Thread


ROOT = Path(__file__).resolve().parent
for module in ("frontend", "middle-office", "ai"):
    sys.path.insert(0, str(ROOT / module))

from UI import create_server
from bff import Gateway, JsonService
from ai_mvp.assistant import Assistant
from ai_mvp.models import from_environment, remote_from_environment
from ai_mvp.profiles import ProfileStore
from ai_mvp.providers import HttpMarketProvider, HttpTradingProvider, QuoteBook
from ai_mvp.server import ApiServer
from middle_office.public_market import PROVIDERS, QUOTE_MAX_AGE, PublicMarketFeed
from middle_office.service import MiddleOffice
from middle_office.server import Server
from middle_office.validation import iso


HOST = "127.0.0.1"
USER = "student_demo"
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
    markets = {
        "BTC/USDT": ("Bitcoin", "比特币", 68000),
        "ETH/USDT": ("Ethereum", "以太币", 3500),
        "SOL/USDT": ("Solana", "索拉纳", 182),
    }
    return {"quotes": [
        {"symbol": symbol, "name": name, "aliases": [alias], "as_of": as_of, "source": source,
         "price": str(mid + offset), "ask": str(mid + offset + 1), "bid": str(mid + offset - 1),
         "fee_rate": rate}
        for symbol, (name, alias, mid) in markets.items()
        for source, offset, rate in (("demo:HashKey", 0, "0.001"), ("demo:OSL", 2, "0.0015"))
    ]}


def start_server(resources, server):
    resources.enter_context(server)
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
    thread.start()
    resources.callback(thread.join)
    resources.callback(server.shutdown)
    return f"http://{HOST}:{server.server_port}"


@contextmanager
def demo_stack(*, ui_port=None, ollama_model=None, enable_deepseek=False, live_market=False):
    with TemporaryDirectory(prefix="harbor-invest-") as directory, ExitStack() as resources:
        db = Path(directory)
        operator, reader, ai_token = (token_urlsafe(24) for _ in range(3))
        office = MiddleOffice(db / "ledger.sqlite3", max_quote_age=QUOTE_MAX_AGE if live_market else 120,
                              public_sources=PROVIDERS if live_market else ())
        server = Server((HOST, 0), office, token=operator, read_token=reader)
        middle_url = start_server(resources, server)
        middle = JsonService("middle_office", middle_url, operator)
        reader_client = JsonService("middle_office", middle_url, reader)
        office.create_account(USER, {
            "initial_balances": {"USDT": "10000"},
            "initial_positions": [{"symbol": "BTC/USDT", "quantity": "0.1", "average_cost": "65000"}],
        })
        if live_market:
            feed = server.public_feed = PublicMarketFeed(office)
            feed.start()
            resources.callback(feed.stop)
        else:
            office.ingest_quotes(demo_quotes())
            start_demo_feed(resources, office)
        market_url = middle_url + "/api"
        assistant = Assistant(
            ProfileStore(db / "profiles.sqlite3"), QuoteBook(),
            model=from_environment(model_name=ollama_model) if ollama_model else None,
            remote_model=remote_from_environment(enabled=True) if enable_deepseek else None,
            market_provider=HttpMarketProvider(market_url, token=reader, include_venues=live_market),
            trading=HttpTradingProvider(market_url, token=reader),
            quote_max_age=QUOTE_MAX_AGE if live_market else 120,
        )
        ai_url = start_server(resources, ApiServer(0, assistant, ai_token))
        ai = JsonService("ai", ai_url, ai_token, timeout=450 if ollama_model or enable_deepseek else 8)
        ui, _ = create_server(Gateway(ai, middle, USER), port=ui_port)
        ui_url = start_server(resources, ui)
        browser = JsonService("frontend", ui_url, timeout=460 if ollama_model or enable_deepseek else 12)
        yield browser, middle, ai, reader_client, ui_url


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
    parser.add_argument("--ollama-model", help="Installed local Ollama model")
    parser.add_argument("--enable-deepseek", action="store_true", help="Opt in to the API-key model")
    parser.add_argument("--live-market", action="store_true", help="use public spot quotes; execution stays simulated")
    args = parser.parse_args()
    try:
        with demo_stack(ui_port=args.port, ollama_model=args.ollama_model, enable_deepseek=args.enable_deepseek,
                        live_market=args.live_market) as stack:
            mode = "public market data, simulated execution" if args.live_market else "offline simulation"
            print(f"Harbor Invest ({mode}): {stack[-1]}/  (Ctrl+C to stop)", flush=True)
            Event().wait()
    except KeyboardInterrupt:
        pass
    except (OSError, ValueError, RuntimeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
