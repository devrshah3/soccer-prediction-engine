"""Download the configured StatsBomb sample through the production adapter."""

from soccer_engine.ingestion import StatsBombOpenDataProvider

if __name__ == "__main__":
    records = StatsBombOpenDataProvider().fetch_matches("37", "281")
    print(f"Downloaded and validated {len(records)} matches with StatsBomb attribution.")
