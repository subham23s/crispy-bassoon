from ingest_reference_pages import ingest

if __name__ == "__main__":
    import argparse, json
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    print(json.dumps(ingest("owasp", "OWASP", "owasp", args.force), indent=2))
