# pmail Roadmap

## Current Status (v0.1.0)
The core system is feature-complete and ready for daily use. The focus now shifts to robustness, reliability, and user experience improvements based on real-world usage.

## Phase 1: Robustness & Reliability (Priority: HIGH)

### 1.1 Error Recovery & Resilience
- [ ] Add retry logic for Playwright PDF generation failures
- [ ] Handle corrupted email files gracefully
- [ ] Improve error messages with actionable recovery hints
- [ ] Add timeout handling for large email processing
- [ ] Create fallback for failed PDF conversion (save as HTML)

### 1.2 Edge Case Handling
- [ ] Handle emails with missing headers (no From, Subject, etc.)
- [ ] Support non-UTF8 email encodings better
- [ ] Handle malformed MIME attachments
- [ ] Deal with extremely large emails (>50MB)
- [ ] Support emails with duplicate Message-IDs

### 1.3 Data Integrity
- [ ] Add data migration system for config/schema changes
- [ ] Implement config file validation on startup
- [ ] Add repair command for corrupted JSON files
- [ ] Create automatic backups before risky operations

## Phase 2: User Experience (Priority: HIGH)

### 2.1 Debugging & Troubleshooting
- [ ] Add `--dry-run` mode to preview actions without executing
- [ ] Create `--debug` flag for verbose logging
- [ ] Add `pmail --doctor` command to diagnose issues
- [ ] Better error messages for common problems (missing Playwright, etc.)

### 2.2 Workflow Management
- [ ] Add `pmail --list-workflows` command
- [ ] Create `pmail --edit-workflow <name>` command
- [ ] Implement workflow import/export functionality
- [ ] Add workflow templates for common patterns (receipts, invoices, etc.)

### 2.3 Learning System Visibility
- [ ] Add `pmail --stats` to show learning statistics
- [ ] Create confidence threshold configuration
- [ ] Show number of training examples per workflow
- [ ] Add option to review/correct past decisions

## Phase 3: Performance & Scalability (Priority: MEDIUM)

### 3.1 Performance Optimization
- [ ] Add caching for email feature extraction
- [ ] Optimize similarity calculations for large history
- [ ] Implement pagination for criteria instances
- [ ] Add option to archive old criteria

### 3.2 Batch Processing
- [ ] Improve handling of multiple tagged emails in mutt
- [ ] Add progress indicator for batch operations
- [ ] Implement parallel processing for multiple emails
- [ ] Add batch PDF generation with single browser instance

## Phase 4: Advanced Features (Priority: LOW)

### 4.1 Smart Learning
- [ ] Implement criteria merging for similar patterns
- [ ] Add automatic cleanup of low-confidence rules
- [ ] Create "workflow suggestions" based on unmatched emails
- [ ] Implement negative examples (explicitly rejected workflows)

### 4.2 Integration Enhancements
- [ ] Support for other email clients (neomutt, aerc)
- [ ] Add webhook support for workflow execution
- [ ] Create REST API for external integrations
- [ ] Support custom workflow actions via plugins

### 4.3 Advanced PDF Features
- [ ] Add PDF merge functionality for multiple attachments
- [ ] Support PDF password protection
- [ ] Implement PDF OCR for scanned documents
- [ ] Add custom PDF templates/styling

## Testing Strategy

### Before v0.2.0 Release
1. **Real-world testing checklist**:
   - [ ] Process 100+ real emails
   - [ ] Test with various email providers (Gmail, Outlook, etc.)
   - [ ] Verify mutt integration on different systems
   - [ ] Test with non-English emails

2. **Stress testing**:
   - [ ] Large email processing (>10MB)
   - [ ] Batch processing of 50+ emails
   - [ ] Concurrent workflow execution
   - [ ] System with 1000+ criteria instances

3. **Error scenario testing**:
   - [ ] Network failures during PDF generation
   - [ ] Disk full scenarios
   - [ ] Corrupted config files
   - [ ] Missing dependencies

## Development Principles

1. **Backward Compatibility**: Never break existing workflows or data
2. **Fail Gracefully**: Always provide clear error messages and recovery options
3. **User Control**: Never execute actions without user confirmation
4. **Data Safety**: Always backup before modifications
5. **Performance**: Keep response time under 2 seconds for typical emails

## Version Planning

### v0.2.0 (Robustness Release)
- Complete Phase 1 (Robustness & Reliability)
- Essential items from Phase 2 (dry-run, doctor command)
- Comprehensive error handling

### v0.3.0 (UX Release)
- Complete Phase 2 (User Experience)
- Basic performance optimizations
- Workflow management commands

### v0.4.0 (Scale Release)
- Complete Phase 3 (Performance & Scalability)
- Advanced learning features
- Production-ready for large deployments

### v1.0.0 (Stable Release)
- Selected features from Phase 4
- Comprehensive documentation
- Plugin system for extensions