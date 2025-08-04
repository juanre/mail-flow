# pmail Testing Checklist

## Before First Use

### 1. Installation Verification
```bash
# Check pmail is accessible
which pmail || echo "pmail not in PATH"

# Verify Playwright installation
playwright install chromium

# Run the demo
python demo.py

# Run tests
python -m pytest tests/ -v
```

### 2. Mutt Integration
Add to `.muttrc`:
```muttrc
# Process single email
macro index,pager \cp "<pipe-message>pmail<enter>" "Process with pmail"

# Process tagged emails  
macro index \cP "<tag-prefix><pipe-message>pmail<enter>" "Process tagged with pmail"
```

## Basic Functionality Tests

### Test 1: First Email (No History)
- [ ] Open mutt, press Ctrl-P on any email
- [ ] Verify default workflows appear
- [ ] Create a new workflow
- [ ] Confirm it saves the decision

### Test 2: PDF Attachment
- [ ] Find email with PDF attachment
- [ ] Create/select a save_pdf workflow
- [ ] Verify PDF is saved to correct directory
- [ ] Check filename is sanitized properly

### Test 3: Email without PDF
- [ ] Find email without attachments (e.g., receipt in body)
- [ ] Use save_pdf workflow
- [ ] Verify email is converted to PDF
- [ ] Check PDF is readable and formatted well

### Test 4: Learning System
- [ ] Process similar emails (e.g., 2-3 invoices)
- [ ] Verify confidence scores increase
- [ ] Check suggestions improve over time

## Edge Cases to Test

### Email Types
- [ ] HTML-only email
- [ ] Plain text email  
- [ ] Email with inline images
- [ ] Email with multiple PDFs
- [ ] Email with non-PDF attachments
- [ ] Very long email (>1000 lines)
- [ ] Email with special characters in subject/from

### Error Scenarios
- [ ] Corrupt email file
- [ ] Email with no Message-ID
- [ ] Email with duplicate Message-ID
- [ ] Directory without write permissions
- [ ] Disk full scenario
- [ ] Cancel workflow creation (Ctrl-C)

### Workflow Actions
- [ ] save_attachment with various patterns (*.pdf, *.jpg, *.*)
- [ ] flag action
- [ ] copy_to_folder action
- [ ] create_todo action

## Performance Tests

### Speed
- [ ] Single email: Should complete in <2 seconds
- [ ] With 100+ criteria: Should still be <3 seconds
- [ ] PDF generation: Should complete in <5 seconds

### Scale  
- [ ] Process 10 emails in sequence
- [ ] Create 20+ workflows
- [ ] Build up 100+ criteria instances

## Integration Tests

### File System
- [ ] Paths with spaces
- [ ] Unicode filenames
- [ ] Very long filenames (>200 chars)
- [ ] Relative vs absolute paths

### Mutt Interaction
- [ ] Single email processing
- [ ] Tagged batch processing
- [ ] Pipe from search results
- [ ] Return to mutt cleanly

## Robustness Checks

### Recovery
- [ ] Kill during PDF generation
- [ ] Corrupt workflows.json - does it recover?
- [ ] Missing config directory
- [ ] Invalid JSON in config files

### Security
- [ ] Try path traversal (../../etc/passwd)
- [ ] Malicious filenames in attachments
- [ ] HTML with JavaScript in emails
- [ ] Very large attachments

## Known Issues to Verify

1. **Playwright Browser**: If not installed, should show helpful error
2. **Large Emails**: Should handle gracefully with size limits
3. **Unicode**: Should work throughout the system
4. **Permissions**: Should fail gracefully with clear messages

## Success Criteria

- [ ] Can process 50+ emails without errors
- [ ] Workflows execute reliably
- [ ] Learning system improves predictions
- [ ] No data loss or corruption
- [ ] Clear error messages when things fail
- [ ] Integrates smoothly with mutt workflow

## Notes Section
(Add your observations here)

### What Works Well:


### Issues Found:


### Improvement Ideas: