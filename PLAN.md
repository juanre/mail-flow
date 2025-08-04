# Implementation Plan for Email Processing Tool

## Overview
This document outlines the implementation plan for a mutt-integrated email processing tool that uses similarity-based criteria matching and learns from user selections over time.

## Phase 1: Core Infrastructure (Foundation)

### 1.1 Enhanced Email Feature Extraction
- Add attachment detection (PDF, DOC, images)
- Extract sender domain and email provider
- Parse common invoice/receipt patterns in subject lines
- Extract key phrases and entities from body

### 1.2 Data Persistence Layer
- Create `~/.pmail/` config directory structure
- Implement `criteria_instances.json` for historical decisions
- Implement `workflows.json` for workflow definitions
- Add backup/versioning for data files

### 1.3 Criteria Instance Model
- Separate CriteriaTemplate (abstract rules) from CriteriaInstance (concrete examples)
- Store: email_id, timestamp, selected_workflow, extracted_features, user_confirmed
- Include negative examples (rejected workflows)

## Phase 2: Similarity Engine

### 2.1 Feature Vector Creation
- Convert email attributes to numerical vectors
- Implement feature weights (configurable importance)
- Handle categorical (sender domain) and continuous (text similarity) features

### 2.2 Similarity Scoring
- Implement multiple similarity metrics (start with cosine similarity)
- Create composite score from multiple features
- Add recency weighting (recent decisions count more)

### 2.3 Workflow Ranking
- Score all workflows against current email
- Consider both positive and negative examples
- Return top N workflows with confidence scores

## Phase 3: User Interface Enhancement

### 3.1 Interactive Workflow Selection
- Show ranked workflows with similarity percentages
- Display why each workflow matched (which criteria)
- Allow creating new workflow if none fit
- Quick key navigation (1-9 for top choices)

### 3.2 Criteria Refinement UI
- After selection, show extracted criteria
- Allow user to modify before saving
- Option to mark as "strong" or "weak" example

## Phase 4: Mutt Integration

### 4.1 Mutt Macro Setup
- Create macro that pipes full email to pmail
- Handle both single emails and tagged sets
- Return status to mutt (success/failure)

### 4.2 Workflow Execution
- Implement actual workflow actions (save_invoice, etc.)
- Add dry-run mode for testing
- Provide execution feedback to user

## Phase 5: Learning & Improvement

### 5.1 Accretion Mechanism
- Track selection accuracy (user corrections)
- Merge similar criteria over time
- Prune rarely-used or incorrect rules

### 5.2 Analytics & Reporting
- Show rule usage statistics
- Identify ambiguous emails (low confidence)
- Suggest rule improvements

## Technical Decisions

### Similarity Algorithm
Start simple with weighted feature matching, evolve to ML if needed

### Storage Format
JSON for human readability, with option to migrate to SQLite later

### Feature Extraction
Use regex patterns initially, consider NLP libraries for advanced extraction

### UI Library
Stick with readline for consistency with mutt's interface

## Implementation Order

1. Start with enhanced email extraction and persistence
2. Build basic similarity matching with manual weights
3. Create the interactive selection UI
4. Implement core workflows (save_invoice)
5. Add mutt integration
6. Iterate on learning/accretion based on real usage

## Key Design Principles

### Soft Criteria
- No hard rules, everything is similarity-based
- Multiple criteria can suggest the same workflow
- User always has final say

### Accretion Over Time
- Every user decision is saved as training data
- System gets better at predicting the right workflow
- Recent decisions weighted more heavily

### Mutt-Friendly
- Fast response time
- Keyboard-driven interface
- Clear visual feedback
- Non-destructive (never modifies original emails)