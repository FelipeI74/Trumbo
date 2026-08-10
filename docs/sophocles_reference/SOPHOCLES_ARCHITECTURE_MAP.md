# Sophocles 2007 — architecture map

This document separates **direct binary evidence** from **architectural inference**.

## Direct class evidence

RTTI in the compiled application exposes the following important classes.

### Core document/editor

- `CSophDoc`
- `CSophView`
- `COutlineView`
- `CParagraph`
- `CDrawPara`
- `CLineSegment`
- `CLineSegmentList`
- `CParaNote`
- `CPage`, `CPageList`, page-format classes

Compiled diagnostic strings include:

- `CSophDoc::ScriptCorrupt1/2`
- `CSophDoc::CuesCorrupt`
- `CSophDoc::ElementsCorrupt`
- `CParagraph::IsCorrupt`
- `CLineSegment::IsCorrupt`
- `COutlineView::OnKeyDown`
- `COutlineView::BeginEdit`
- caret-related diagnostics in `COutlineView`

### Explorer/navigation views

- `CExplorerView`
- `CHeaderExplorerView`
- `CCharacterExplorerView`
- `CLocationExplorerView`
- `CResourceExplorerView`
- `CThreadExplorerView`
- `CTimelineExplorerView`

A command string explicitly says: `Synchronize Explorer Window to current position`.

### Story/structure views

- `CStepView`
- `CChronoView`
- `CChartView`
- `CRelationsDlg`
- `CThread`, `CThreadPicker`
- `CStep`

### Breakdown and production

- `CBreakdownDlg`
- `CBreakdownPage`
- `CBreakdownGrid`
- `CBreakdownCharacters`
- `CBreakdownHeaders`
- `CBreakdownOther`

### Resources

- `CResource`
- `CCharacterResource`
- `CLocationResource`
- `CSetResource`
- `CResourceExplorerView`
- resource property/list/sheet classes

### Scheduling

- `CScheduleView`
- `CAutoScheduleDlg`
- `CAutoSchedulePreDlg`
- availability classes
- `CDaysOff`
- `CCallDateDlg`
- `CCallTimeDlg`
- schedule report option classes

### Budgeting

A large family of `CBudget*` classes exists, including accounts, resources, fringes, quantities/rates, units, parent/sum/percent accounts and report options.

## Architectural inference

The class layout strongly supports the following model:

```text
CSophDoc                         <- central project/document model
  |
  +-- paragraphs / line segments
  +-- cues / elements / resources
  +-- production units
  +-- pages / revisions

CSophView / COutlineView         <- main screenplay editing/rendering layer

Explorer views                  <- alternate navigational projections
  +-- Scenes/Headers
  +-- Characters
  +-- Locations
  +-- Resources
  +-- Threads/Timeline

Detail / Breakdown views        <- metadata attached to screenplay structure

ScheduleView                    <- scheduling projection over production data
```

The key point for Trumbo is not the MFC class design itself. The useful principle is that the screenplay document, its paragraphs, explorers, breakdown and schedule are integrated projections of shared project data rather than unrelated applications.

## Trumbo mapping

Recommended clean mapping:

```text
Trumbo Screenplay Document
  -> semantic lines/blocks
  -> derived Scenes
  -> Characters / Locations / Resources
  -> Engine events and production knowledge
  -> Breakdown
  -> Scheduling
```

The Engine is an extension Sophocles did not have: it should automate extraction and proposals while keeping the proven editor workflow intact.
