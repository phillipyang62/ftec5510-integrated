import argparse
import json
import os

from .market import MarketFeed
from .price_history import CHART_PAIRS
from .public_market import PROVIDER_MARKETS, QUOTE_MAX_AGE, PublicMarketFeed
from .service import MiddleOffice
from .server import Server


def main():
    parser = argparse.ArgumentParser(description="Group 20 middle office (simulation)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8200)
    parser.add_argument("--db")
    parser.add_argument("--quote-max-age", type=int)
    parser.add_argument("--market-url", default=os.getenv("MO_MARKET_URL"), help="upstream quote URL returning {quotes:[...]}")
    parser.add_argument("--market-interval", type=int, default=5)
    parser.add_argument("--public-market", action="store_true", help="collect public exchange spot quotes")
    parser.add_argument("--product-risks", help="JSON mapping pairs to risk grades or to grade and requirements")
    parser.add_argument("--suitability-advisory", action="store_true", help="report assessment warnings on simulated buys")
    args = parser.parse_args()
    policy = {}
    if args.product_risks:
        with open(args.product_risks, encoding="utf-8-sig") as file:
            policy = json.load(file)
    if not isinstance(policy, dict):
        parser.error("--product-risks must contain a JSON object")
    risks = {symbol: entry.get("grade") if isinstance(entry, dict) else entry for symbol, entry in policy.items()}
    requirements = {symbol: entry.get("requirements", {}) for symbol, entry in policy.items() if isinstance(entry, dict)}
    if args.public_market and args.market_url:
        parser.error("choose --public-market or a custom market URL")
    database = args.db or (".middle_office/public-ledger.sqlite3" if args.public_market else ".middle_office/ledger.sqlite3")
    quote_age = args.quote_max_age if args.quote_max_age is not None else (QUOTE_MAX_AGE if args.public_market else 120)
    sources = PROVIDER_MARKETS if args.public_market else {}
    office = MiddleOffice(database, max_quote_age=quote_age, product_risks=risks, public_sources=sources,
                          public_source_pairs=sources, product_requirements=requirements,
                          chart_pairs=CHART_PAIRS | requirements.keys(),
                          suitability_advisory=args.suitability_advisory)
    server = Server((args.host, args.port), office, token=os.getenv("MO_API_TOKEN"), read_token=os.getenv("MO_AI_READ_TOKEN"))
    feed = None
    if args.public_market:
        feed = server.public_feed = PublicMarketFeed(office, interval=args.market_interval)
    elif args.market_url:
        feed = MarketFeed(office, args.market_url, token=os.getenv("MO_MARKET_TOKEN"), interval=args.market_interval)
    if feed:
        feed.start()
    print(f"Middle office listening at http://{args.host}:{server.server_port} (simulation)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if feed:
            feed.stop()
        server.server_close()


if __name__ == "__main__":
    main()
