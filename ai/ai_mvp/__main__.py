import argparse
import os
from pathlib import Path

from .assistant import Assistant
from .models import from_environment, remote_from_environment
from .profiles import ProfileStore
from .providers import HttpMarketProvider, HttpTradingProvider, QuoteBook
from .server import ApiServer


def main():
    parser = argparse.ArgumentParser(description="Run the local AI MVP")
    parser.add_argument("--host", default="127.0.0.1", help="IPv4 address to listen on")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db", type=Path, default=Path(".ai_mvp/profiles.sqlite3"))
    parser.add_argument("--ollama-model", help="name of an installed local Ollama model")
    parser.add_argument("--enable-remote", action="store_true", help="enable the configured API-key model")
    args = parser.parse_args()
    api_token = os.getenv("AI_MVP_API_TOKEN")
    market_url = os.getenv("AI_MVP_MARKET_URL")
    trading_url = os.getenv("AI_MVP_TRADING_URL")
    if trading_url and not api_token:
        parser.error("AI_MVP_API_TOKEN is required when configuring the middle office")
    try:
        quote_max_age = int(os.getenv("AI_MVP_QUOTE_MAX_AGE_SECONDS", "120"))
        if quote_max_age < 1:
            raise ValueError("AI_MVP_QUOTE_MAX_AGE_SECONDS must be positive")
        model = from_environment(model_name=args.ollama_model)
        remote_model = remote_from_environment(enabled=args.enable_remote)
        market = HttpMarketProvider(market_url, token=os.getenv("AI_MVP_MARKET_TOKEN"),
                                    include_venues=os.getenv("AI_MVP_MARKET_ALL_SOURCES") == "1") if market_url else None
        trading = HttpTradingProvider(trading_url, token=os.getenv("AI_MVP_TRADING_TOKEN")) if trading_url else None
    except ValueError as error:
        parser.error(str(error))

    args.db.parent.mkdir(parents=True, exist_ok=True)
    assistant = Assistant(ProfileStore(args.db), QuoteBook(), model, trading, quote_max_age,
                          remote_model=remote_model, market_provider=market)
    try:
        server = ApiServer(args.port, assistant, api_token, host=args.host)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    with server:
        print(f"AI MVP listening on http://{server.server_address[0]}:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
