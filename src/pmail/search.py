#!/usr/bin/env python
"""
Search tool for pmail metadata databases.
"""
import argparse
import sys
from pathlib import Path
from typing import Optional

from pmail.metadata_store import MetadataStore


def search_pdfs(directory: str, query: str = None, limit: int = 20, doc_type: str = None):
    """Search PDFs in a directory."""
    try:
        store = MetadataStore(directory)

        if doc_type:
            results = store.search_by_type(doc_type, limit)
            search_desc = f"document type '{doc_type}'"
        else:
            results = store.search(query, limit)
            search_desc = f"'{query}'"

        if not results:
            print(f"No results found for {search_desc}")
            return

        print(f"\nFound {len(results)} results for {search_desc}:\n")

        for i, result in enumerate(results, 1):
            print(f"{i}. {result['filename']}")
            print(f"   Subject: {result['email_subject']}")
            print(f"   From: {result['email_from']}")
            print(f"   Date: {result['email_date']}")
            print(f"   Path: {result['filepath']}")
            print(f"   Type: {result['pdf_type']}")
            if result.get("document_type"):
                print(f"   Document Type: {result['document_type']}")
            if result.get("document_category"):
                print(f"   Category: {result['document_category']}")
            print()

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def show_stats(directory: str):
    """Show statistics for a directory."""
    try:
        store = MetadataStore(directory)
        stats = store.get_statistics()

        print(f"\nStatistics for {directory}:\n")
        print(f"Total PDFs: {stats.get('total_pdfs', 0)}")
        print(f"Total size: {stats.get('total_size_mb', 0):.1f} MB")

        if stats.get("by_pdf_type"):
            print("\nBy PDF type:")
            for pdf_type, count in stats["by_pdf_type"].items():
                print(f"  {pdf_type}: {count}")

        if stats.get("by_document_type"):
            print("\nBy document type:")
            for doc_type, count in stats["by_document_type"].items():
                print(f"  {doc_type}: {count}")

        if stats.get("by_category"):
            print("\nBy category:")
            for category, count in stats["by_category"].items():
                print(f"  {category}: {count}")

        if stats.get("by_workflow"):
            print("\nBy workflow:")
            for workflow, count in stats["by_workflow"].items():
                print(f"  {workflow}: {count}")

        if stats.get("by_year"):
            print("\nBy year:")
            for year, count in sorted(stats["by_year"].items(), reverse=True):
                print(f"  {year}: {count}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def check_duplicate(directory: str, message_id: str):
    """Check if a message has already been saved."""
    try:
        store = MetadataStore(directory)
        results = store.get_by_message_id(message_id)

        if not results:
            print(f"No PDFs found for message ID: {message_id}")
            return

        print(f"\nFound {len(results)} PDFs for message ID {message_id}:\n")

        for result in results:
            print(f"- {result['filename']}")
            print(f"  Saved: {result['saved_at']}")
            print(f"  Path: {result['filepath']}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    """Main entry point for search tool."""
    parser = argparse.ArgumentParser(
        description="Search pmail PDF metadata",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Search for invoices from amazon
  %(prog)s ~/receipts "amazon invoice"
  
  # Search by document type
  %(prog)s ~/receipts --type invoice
  
  # Show statistics
  %(prog)s ~/receipts --stats
  
  # Check if email was already saved
  %(prog)s ~/receipts --check-message-id "<msg-123@example.com>"
""",
    )

    parser.add_argument("directory", help="Directory containing PDFs and metadata")

    parser.add_argument("query", nargs="?", help="Search query")

    parser.add_argument(
        "-l", "--limit", type=int, default=20, help="Maximum results to show (default: 20)"
    )

    parser.add_argument(
        "-s", "--stats", action="store_true", help="Show statistics instead of searching"
    )

    parser.add_argument("-m", "--check-message-id", help="Check if message ID has been saved")

    parser.add_argument(
        "-t", "--type", help="Search by document type (e.g., invoice, receipt, tax)"
    )

    args = parser.parse_args()

    # Validate directory
    if not Path(args.directory).exists():
        print(f"Error: Directory '{args.directory}' does not exist", file=sys.stderr)
        sys.exit(1)

    # Execute requested action
    if args.stats:
        show_stats(args.directory)
    elif args.check_message_id:
        check_duplicate(args.directory, args.check_message_id)
    elif args.type:
        search_pdfs(args.directory, None, args.limit, doc_type=args.type)
    elif args.query:
        search_pdfs(args.directory, args.query, args.limit)
    else:
        parser.error("Please provide a query or use --stats/--check-message-id/--type")


if __name__ == "__main__":
    main()
