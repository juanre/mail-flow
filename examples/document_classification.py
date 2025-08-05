#!/usr/bin/env python
"""
Example of using document classification and metadata extraction with pmail.

This example demonstrates:
1. Automatic document type classification
2. Storing structured document information
3. Searching by document type
4. Updating document metadata
"""

from pathlib import Path
from pmail.metadata_store import MetadataStore, DocumentType, DocumentCategory

def main():
    # Create a test directory
    test_dir = Path("/tmp/pmail_example")
    test_dir.mkdir(exist_ok=True)
    
    # Initialize metadata store
    store = MetadataStore(str(test_dir))
    
    # Example 1: Store an invoice with automatic classification
    print("=== Example 1: Automatic Classification ===")
    
    invoice_email = {
        "message_id": "<invoice-123@amazon.com>",
        "from": "billing@amazon.com",
        "to": "customer@example.com",
        "subject": "Invoice #INV-2024-001 - Payment Due",
        "date": "Mon, 15 Jan 2024 10:00:00 +0000",
        "body": "Your invoice for order #12345 is attached. Amount due: $99.99"
    }
    
    # Create a fake PDF
    pdf_path = test_dir / "2024-01-15-amazon-invoice.pdf"
    pdf_path.write_text("Fake PDF content")
    
    # Get suggested classification
    doc_type, doc_category = MetadataStore.suggest_document_classification(invoice_email)
    print(f"Suggested type: {doc_type}, category: {doc_category}")
    
    # Store with classification and extracted info
    store.store_pdf_metadata(
        pdf_path=pdf_path,
        email_data=invoice_email,
        workflow_name="invoices",
        document_type=doc_type,
        document_category=doc_category,
        document_info={
            "vendor": "Amazon",
            "amount": 99.99,
            "currency": "USD",
            "invoice_number": "INV-2024-001",
            "order_number": "12345"
        }
    )
    
    # Example 2: Update document information
    print("\n=== Example 2: Updating Document Info ===")
    
    store.update_document_info(
        message_id="<invoice-123@amazon.com>",
        filename="2024-01-15-amazon-invoice.pdf",
        document_info={
            "paid": True,
            "payment_date": "2024-01-20",
            "payment_method": "Credit Card"
        }
    )
    
    # Retrieve updated info
    doc_info = store.get_document_info(
        "<invoice-123@amazon.com>",
        "2024-01-15-amazon-invoice.pdf"
    )
    print(f"Document info: {doc_info}")
    
    # Example 3: Store multiple documents
    print("\n=== Example 3: Multiple Documents ===")
    
    documents = [
        {
            "email": {
                "message_id": "<receipt-456@walmart.com>",
                "from": "receipts@walmart.com",
                "subject": "Your Walmart Receipt",
                "body": "Thank you for shopping at Walmart!"
            },
            "info": {"vendor": "Walmart", "amount": 45.67}
        },
        {
            "email": {
                "message_id": "<tax-789@irs.gov>",
                "from": "noreply@irs.gov",
                "subject": "Your 1099 Tax Form",
                "body": "Your tax documents are ready."
            },
            "info": {"form_type": "1099-MISC", "tax_year": 2023}
        },
        {
            "email": {
                "message_id": "<statement-101@bank.com>",
                "from": "statements@bank.com",
                "subject": "Monthly Statement",
                "body": "Your account statement is ready."
            },
            "info": {"account_ending": "1234", "balance": 5000.00}
        }
    ]
    
    for i, doc in enumerate(documents):
        # Create PDF
        filename = f"doc-{i}.pdf"
        pdf_path = test_dir / filename
        pdf_path.write_text("Fake PDF")
        
        # Get classification
        doc_type, doc_cat = MetadataStore.suggest_document_classification(doc["email"])
        
        # Store with metadata
        store.store_pdf_metadata(
            pdf_path=pdf_path,
            email_data=doc["email"],
            workflow_name="general",
            document_type=doc_type,
            document_category=doc_cat,
            document_info=doc["info"]
        )
    
    # Example 4: Search by document type
    print("\n=== Example 4: Search by Type ===")
    
    invoices = store.search_by_type(DocumentType.INVOICE)
    print(f"Found {len(invoices)} invoices")
    
    receipts = store.search_by_type(DocumentType.RECEIPT)
    print(f"Found {len(receipts)} receipts")
    
    tax_docs = store.search_by_type(DocumentType.TAX)
    print(f"Found {len(tax_docs)} tax documents")
    
    # Example 5: Get statistics
    print("\n=== Example 5: Statistics ===")
    
    stats = store.get_statistics()
    print(f"Total PDFs: {stats['total_pdfs']}")
    print(f"By document type: {stats['by_document_type']}")
    print(f"By category: {stats['by_category']}")
    
    # Example 6: Full-text search
    print("\n=== Example 6: Full-Text Search ===")
    
    results = store.search("amazon")
    print(f"Found {len(results)} documents mentioning 'amazon'")
    
    for result in results:
        print(f"  - {result['filename']} ({result['document_type']})")


if __name__ == "__main__":
    main()