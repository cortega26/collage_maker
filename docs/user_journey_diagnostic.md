# App User Journey Diagnostic

## Persona Profiles

1. **Rosa Delgado – Freelance Social Media Manager**  
   *Context:* Runs multiple brand accounts, assembles daily promotional collages.  
   *Job-to-be-done:* Rapidly assemble on-brand collages from client assets and export in multiple formats.  
   *Motivation / Success:* Produce polished collages within minutes without rework; maintain consistency across campaigns.  
   *Tech comfort:* High.

2. **Malik Owens – Wedding Photographer**  
   *Context:* Processes hundreds of RAW/JPEG photos per event, creates teaser collages for clients.  
   *Job-to-be-done:* Import large photo batches, curate highlights, and export in high resolution with minimal manual cleanup.  
   *Motivation / Success:* Showcase best shots quickly while preserving quality and metadata.  
   *Tech comfort:* Medium.

3. **Priya Shah – Marketing Intern (First-time User)**  
   *Context:* Asked to create social posts; limited design experience, nervous about messing up assets.  
   *Job-to-be-done:* Follow a checklist to build her first collage and deliver it without mistakes.  
   *Motivation / Success:* Complete the task confidently with guidance and avoid sending something off-brand.  
   *Tech comfort:* Medium-low.

4. **Ethan Price – Community Manager with Accessibility Needs**  
   *Context:* Low-vision user relying on keyboard navigation and high-contrast UI.  
   *Job-to-be-done:* Update recurring collage templates for weekly reports without fighting the UI.  
   *Motivation / Success:* Work efficiently using keyboard, trust that UI respects accessibility settings.  
   *Tech comfort:* Medium-high.

5. **Linda Cho – Small Business Owner on Low-Spec Laptop**  
   *Context:* Runs DIY marketing on aging hardware; switches between tasks constantly.  
   *Job-to-be-done:* Create occasional promotional collages without bogging down her computer.  
   *Motivation / Success:* Avoid crashes/slowdowns, finish collages quickly between other tasks.  
   *Tech comfort:* Medium.

## Journeys & Diagnostics

### Rosa Delgado – Freelance Social Media Manager

| Journey Stage | User Goal at this Stage | Current Pain / Gap (Be blunt) | Severity (H/M/L) | Proposed Fix (Specific) | Expected Impact (User + Business) |
|---------------|------------------------|--------------------------------|------------------|--------------------------|-----------------------------------|
| Entry / Discovery | Confirm the app can export on-brand assets fast | Marketing copy never mentions batch export presets; she assumes manual reconfiguration each time | M | **Docs update**: Add “Save preset exports” section with clear CTA in onboarding tooltip linking to template save feature | Sets correct expectation, reduces bounce to competitors, higher trial-to-adopt conversion |
| Onboarding / Setup | Load template, import folders quickly | “Add Images” dialog forgets last-used folder; re-navigating client drive each session | H | **Improved default**: Persist last used import directory per session in settings.ini via existing config manager | Cuts onboarding time, reduces churn during busy days; increases daily active use |
| Core Usage | Rapid drag-drop, apply captions, export variations | Undo stack drops caption changes when switching templates; forces redo from scratch | H | **Bug fix**: Ensure `_capture_for_undo()` fires when caption toggles triggered via toolbar (currently only context menu) | Restores trust in undo, prevents lost work → higher retention |
| Retention / Return | Maintain saved presets, rely on autosave | Autosave lacks explicit status indicator; she assumes save failed and manually duplicates exports | M | **UI addition**: Add autosave status icon + tooltip in status bar | Boosts trust, reduces duplicate exports (saves time, reduces support tickets) |
| Support / Escalation | Resolve export color profile doubts | No knowledge base article; must email support to confirm sRGB handling | M | **Docs addition**: Create FAQ entry about export color profiles & proofing | Decreases support load, speeds user reassurance |

### Malik Owens – Wedding Photographer

| Journey Stage | User Goal at this Stage | Current Pain / Gap (Be blunt) | Severity (H/M/L) | Proposed Fix (Specific) | Expected Impact (User + Business) |
|---------------|------------------------|--------------------------------|------------------|--------------------------|-----------------------------------|
| Entry / Discovery | Verify high-res export & RAW support | Landing page only touts social media use; doubts suitability for pro work | M | **Marketing copy tweak**: Add bullet about high-resolution, 300 DPI export & RAW-to-JPEG pipeline | Expands funnel to prosumers, increases conversion |
| Onboarding / Setup | Import large folder, trim to highlights | Import dialog lacks progress feedback; appears frozen on 200+ photos | H | **Progress UI**: Show determinate progress bar tied to worker queue when importing >20 files | Prevents hard exits, reduces rage quit |
| Core Usage | Compare images, select best angles | No multi-select compare mode; must open each cell, wasting time | M | **New helper**: Add “Quick compare” split preview when two cells selected (reuse existing zoom panel) | Speeds curation, increases satisfaction, reduces churn |
| Retention / Return | Save client presets for reuse | Template presets stored locally only; moving to studio desktop resets everything | M | **Feature extension**: Enable export/import of template presets to JSON | Encourages loyalty, adds upsell opportunity |
| Support / Escalation | Report crashes on large batches | Crash dialog offers generic “unexpected error” without log hint | H | **Error UX**: Add crash reporter dialog with log file path + copy button | Improves trust, enables faster fixes, less churn |

### Priya Shah – Marketing Intern (First-time User)

| Journey Stage | User Goal at this Stage | Current Pain / Gap (Be blunt) | Severity (H/M/L) | Proposed Fix (Specific) | Expected Impact (User + Business) |
|---------------|------------------------|--------------------------------|------------------|--------------------------|-----------------------------------|
| Entry / Discovery | Understand tool fits her assignment | Website assumes prior design knowledge; no “first collage” example | M | **Starter template download**: Provide annotated walkthrough sample on homepage | Converts nervous newcomers, lowers bounce |
| Onboarding / Setup | Get through first run without errors | Onboarding wizard skips validation; she imports mixed formats and gets silent skips | H | **Validation messaging**: Surface inline warnings listing unsupported files with suggested fixes | Prevents confusion, fewer support tickets |
| Core Usage | Follow checklist to edit captions | Caption toolbar dense; icons unlabeled unless hovered, keyboard focus unclear | H | **UI tweak**: Add text labels under critical caption buttons + highlight focus state | Reduces misclicks, boosts task completion |
| Retention / Return | Feel confident repeating task | No “what’s new” or tips panel; she forgets keyboard shortcuts and reverts to Canva | M | **In-app tips carousel**: Rotating helper banner after export summarizing shortcuts | Encourages repeat usage |
| Support / Escalation | Ask for help | Help menu buries tutorial video three levels deep | M | **Menu restructure**: Pin “Getting Started (3 min video)” to Help top level | Lowers support emails, improves onboarding |

### Ethan Price – Community Manager with Accessibility Needs

| Journey Stage | User Goal at this Stage | Current Pain / Gap (Be blunt) | Severity (H/M/L) | Proposed Fix (Specific) | Expected Impact (User + Business) |
|---------------|------------------------|--------------------------------|------------------|--------------------------|-----------------------------------|
| Entry / Discovery | Confirm accessibility compliance | No mention of keyboard support or high-contrast theme in docs | M | **Docs addition**: Accessibility section describing shortcuts & contrast ratios | Builds trust, avoids churn |
| Onboarding / Setup | Configure high-contrast theme, keyboard nav | Theme toggle hidden in settings.ini; requires manual edit | H | **Settings UI**: Surface theme toggle in preferences dialog with preview | Immediate usability, wider adoption |
| Core Usage | Operate fully via keyboard & screen reader | Focus order skips toolbar toggles; screen reader labels missing | H | **Accessibility audit**: Add `accessibleName`/`accessibleDescription`, fix tab order in toolbar creation | Enables core task completion, reduces ADA risk |
| Retention / Return | Trust autosave and undo with assistive tech | Status messages appear only visually; no audio or focus alerts | M | **ARIA-style feedback**: Trigger announcer (status QAccessible::updateAccessibility) for autosave/undo | Retains accessible users, mitigates legal exposure |
| Support / Escalation | Report accessibility bug | No dedicated accessibility support channel; general inbox slow | M | **Support routing**: Add `Accessibility Feedback` mailto shortcut with template | Shows commitment, reduces PR risk |

### Linda Cho – Small Business Owner on Low-Spec Laptop

| Journey Stage | User Goal at this Stage | Current Pain / Gap (Be blunt) | Severity (H/M/L) | Proposed Fix (Specific) | Expected Impact (User + Business) |
|---------------|------------------------|--------------------------------|------------------|--------------------------|-----------------------------------|
| Entry / Discovery | Ensure app runs on old hardware | System requirements hidden in docs; she fears slowdowns | M | **Docs clarity**: Add system requirements block with minimal specs | Reduces anxiety, increases installs |
| Onboarding / Setup | Launch quickly without freezes | First launch preloads all templates; CPU spikes, fans spin, she assumes crash | H | **Performance optimization**: Lazy-load template previews after UI idle via worker | Prevents drop-off, better reviews |
| Core Usage | Swap images while multitasking | Background autosave locks UI for seconds during exports | H | **Worker offload**: Move autosave IO to background thread with progress lock indicator | Stops hangs, keeps trust |
| Retention / Return | Avoid data loss | Autosave directory grows; no cleanup → disk fills on small SSD | M | **Maintenance feature**: Add “Manage autosave storage” dialog with cleanup | Improves retention, reduces support tickets |
| Support / Escalation | Get help after slowdown | Support FAQ doesn’t address performance tweaks for low-spec machines | M | **FAQ entry**: “Optimize for older PCs” with step-by-step settings | Empowers users, lowers churn |

## Highest-Leverage Fixes (Do These First)

- **Fix #1:** Persist last-used import directory and show progress on bulk imports  
  - Personas affected: Rosa Delgado, Malik Owens, Linda Cho  
  - Journey stage: Onboarding / Setup  
  - Current pain / business risk: Users think app is frozen or slog through repeated navigation, leading to abandonment under time pressure.  
  - Expected outcome: Higher onboarding completion, reduced rage quits, stronger first-session retention.  
  - Effort: Medium.

- **Fix #2:** Repair undo/caption history capture and add accessibility-friendly toolbar labelling  
  - Personas affected: Rosa Delgado, Priya Shah, Ethan Price  
  - Journey stage: Core Usage  
  - Current pain / business risk: Lost work and inaccessible controls destroy trust; users churn to alternative tools.  
  - Expected outcome: Reliable editing, higher daily active use, mitigated accessibility compliance risk.  
  - Effort: Medium.

- **Fix #3:** Offload autosave/export IO to background with visible status + cleanup controls  
  - Personas affected: Rosa Delgado, Linda Cho  
  - Journey stage: Core Usage & Retention  
  - Current pain / business risk: UI freezes and disk bloat trigger churn and negative word-of-mouth.  
  - Expected outcome: Smooth editing on low-spec machines, improved retention, fewer support tickets.  
  - Effort: High.
