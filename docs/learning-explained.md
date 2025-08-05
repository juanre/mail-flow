# How pmail Learns: The 800 Email Journey

## What Changes After 800 Emails?

### 1. **File Changes**

#### `~/.config/pmail/criteria_instances.json`
- **Start**: Empty `[]`
- **After 800 emails**: ~800 training examples (one per decision)
- **Size**: ~2-5 MB depending on email complexity

Example growth:
```json
[
  // Email #1 - No confidence, creating new workflow
  {
    "email_id": "msg-001@amazon.com",
    "workflow_name": "save-invoices", 
    "confidence_score": 0.0,  // First time, no history
    "email_features": {...}
  },
  
  // Email #50 - Starting to see patterns
  {
    "email_id": "msg-050@amazon.com",
    "workflow_name": "save-invoices",
    "confidence_score": 0.65,  // Getting better!
    "email_features": {...}
  },
  
  // Email #800 - High confidence predictions
  {
    "email_id": "msg-800@utility.com", 
    "workflow_name": "save-bills",
    "confidence_score": 0.92,  // Very confident now
    "email_features": {...}
  }
]
```

#### `~/.config/pmail/workflows.json`
- **Start**: 3 default workflows
- **After 800 emails**: Probably 10-20 workflows for different email types
- Each workflow tailored to specific patterns you've identified

### 2. **Prediction Accuracy Improves**

#### Day 1 (0-10 emails)
```
Processing email from noreply@github.com
No similar workflows found in history.

Options:
  'skip' to skip this email
  'new' to create a new workflow
```

#### Day 30 (200 emails)
```
Processing email from noreply@github.com
Suggested workflows (based on similarity):
  1. archive-notifications (45%)
     Matches because: Same sender domain: github.com
  2. flag-important (15%)
```

#### Day 90 (800 emails)
```
Processing email from noreply@github.com
Suggested workflows (based on similarity):
  1. archive-notifications (89%) [default: 1]
     Matches because: Same sender domain: github.com, Similar subject words: pull, request, merged
  2. github-prs (75%)
     Matches because: Similar subject words: pull, request
```

### 3. **Pattern Recognition Examples**

After 800 emails, pmail recognizes complex patterns:

#### Invoice Detection
- Amazon invoices → `save-personal-receipts` (95% confidence)
- Utility bills → `save-household-bills` (92% confidence)
- Business invoices → `save-business-expenses` (88% confidence)

The system learns YOUR specific patterns:
- You save Amazon orders to personal receipts
- But AWS invoices go to business expenses
- It learns this distinction from your choices!

#### Newsletter Management
- Technical newsletters → `archive-reading`
- Marketing emails → `skip`
- Important updates → `flag-important`

### 4. **What Makes It "Smarter"**

#### More Training Data = Better Predictions
```python
# With 10 examples: rough patterns
if from_domain == "amazon.com" and has_pdf:
    suggest "save-invoices" (60% confidence)

# With 800 examples: nuanced understanding  
if from_domain == "amazon.com" and has_pdf:
    if subject contains "AWS":
        suggest "save-business-expenses" (94%)
    elif subject contains "Order":
        suggest "save-personal-receipts" (91%)
    elif body contains "Kindle":
        suggest "save-digital-receipts" (88%)
```

#### Learned Distinctions
The system learns YOUR specific categorizations:
- **Same sender, different workflows**: 
  - `billing@verizon.com` + "Invoice" → `save-bills`
  - `billing@verizon.com` + "Payment received" → `archive`

- **Similar emails, different handling**:
  - PDF invoices from vendors → `save-invoices` 
  - PDF reports from vendors → `archive-reports`

### 5. **No Decay = Permanent Learning**

Unlike the original plan, we removed time-based decay:
```python
# No recency weighting - all criteria are equally valid regardless of age
# Older criteria may even be more valuable as they've proven useful over time
```

This means:
- First invoice from 6 months ago: Still valuable for matching
- Seasonal patterns: Remembers tax documents from last year
- Rare emails: Even if you only see them quarterly, it remembers

### 6. **Practical Impact**

#### Workflow Creation Frequency
- **First week**: Creating new workflows daily
- **First month**: Creating 1-2 per week  
- **After 800 emails**: Rarely create new ones

#### Time Saved
- **Initial processing**: 30-60 seconds per email (deciding what to do)
- **After 800 emails**: 2-5 seconds (just press Enter for high-confidence matches)

#### Confidence Distribution (typical after 800 emails)
- 40% of emails: >85% confidence (just press Enter)
- 30% of emails: 60-85% confidence (usually right, occasionally adjust)
- 20% of emails: 30-60% confidence (suggestions help but need review)
- 10% of emails: <30% confidence (new types, need new workflow)

## The Learning Never Stops

Even after 800 emails:
- New senders appear → System adapts
- Email formats change → Learns new patterns
- You change preferences → Adjusts predictions

The key insight: **pmail learns YOUR email patterns, not generic rules**. Two users processing the same 800 emails would have completely different learned behaviors based on their workflow choices.