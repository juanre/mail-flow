# How mailflow Learns

## Classification Strategy

mailflow uses a **hybrid approach** combining similarity matching and optional LLM classification:

### 1. Similarity-Based Learning
- Extracts features from each email: sender domain, subject keywords, attachments, body content
- Compares new emails to past classifications using Jaccard similarity
- Calculates weighted scores based on feature matches
- Suggests workflows based on highest similarity scores

### 2. LLM Enhancement (Optional)
When enabled, LLM provides AI-powered classification:
- **High confidence (≥85%)**: Uses similarity only (fast, free)
- **Medium confidence (50-85%)**: Shows both similarity and AI suggestions
- **Low confidence (<50%)**: Uses AI as primary suggestion

### 3. Continuous Improvement
Every workflow selection creates a training example:
```json
{
  "email_id": "msg-123@example.com",
  "workflow_name": "business-receipts",
  "email_features": {
    "from_domain": "aws.amazon.com",
    "subject_words": ["invoice", "aws"],
    "has_pdf": true
  }
}
```

These accumulate in `criteria_instances.json` and improve future predictions.

## Learning Over Time

**First Week**: Creating workflows, low confidence predictions
**First Month**: 60-70% confidence on common patterns
**After Hundreds**: 85%+ confidence on most emails, rare workflow creation

## Feature Weights

Default configuration (adjustable in config.json):
```json
{
  "from_domain": 0.3,        # Sender domain most important
  "subject_similarity": 0.25, # Subject keywords
  "has_pdf": 0.2,            # Attachment presence
  "body_keywords": 0.15,     # Body content
  "to_address": 0.1          # Recipient
}
```

## Deduplication

Tracks all processed emails in `processed_emails.db`:
- Primary: Email Message-ID
- Fallback: MD5 hash of content

Prevents reprocessing duplicates unless `--force` is used.

## No Time Decay

All training examples are equally valuable regardless of age. This preserves:
- Seasonal patterns (tax documents from last year)
- Rare senders (quarterly bills)
- Historical context (proven successful patterns)
