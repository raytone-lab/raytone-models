# Raytone Models — interface system

Reference: [12 full-size mockups](mockups/index.html). Six screen pairs, dark left and light right; each application window is **1200 × 760 logical pixels** including the 39 px title bar. The canvas intentionally scrolls horizontally rather than scaling the application. English labels reserve space for future CJK text. The document is fully offline, with inline CSS and SVG, no scripts, fonts, or network requests. Controls are static visual references except in-document navigation, radio selection, and native input/select behavior.

## Principles and information architecture

Calm, precise local infrastructure. Navy supplies the structure; gold identifies the next action. Rounded horizontal controls echo the symbol’s bars without imitating the logo. No gradients, glass, glow, decorative dashboard noise, or web-specific rendering is required.

Persistent navigation: Recipes (default), Local models, Discover, Running, Agents, Engines. Keep the 196 px rail stable between screens. Main content uses 28 px horizontal padding, 26 px top padding, and a 22 px header gap. The window border is 1 px, radius 16 px. At this reference size, long data lists scroll inside their allocated panes; the title and navigation remain visible. Implementation must permit text scaling and scrolling rather than reproduce clipped content at larger system font sizes.

## Colour tokens

| Token | Dark | Light | Usage |
|---|---|---|---|
| background | `#111C32` | `#F6F7FA` | Main canvas |
| rail | `#0D172B` | `#EDF0F5` | Navigation |
| surface | `#182649` | `#FFFFFF` | Cards and lists |
| raised | `#1E3052` | `#F0F3F8` | Selected rows, contextual information |
| text | `#F1F4FA` | `#162547` | Main text |
| muted | `#AEBBD1` | `#52617A` | Secondary text; never use opacity to dim text |
| border | `#3D5071` | `#8997AE` | Separators and outlines |
| accent | `#DFAE39` | `#DFAE39` | Primary actions, active navigation, progress |
| onAccent | `#182649` | `#182649` | Text and icons on gold |
| focus | `#F2C966` | `#806018` | 2 px keyboard focus outline, 3 px offset |
| readyText / readyFill | `#9EDBBB` / `#203D39` | `#246044` / `#E6F2EB` | Ready, connected, running |
| pendingText / pendingFill | `#F2CE87` / `#423723` | `#765217` / `#FBEFDA` | Downloading, starting, incomplete |
| errorText / errorFill | `#F4B3B8` / `#432C3C` | `#9E3547` / `#FBE9EC` | Conflict, error, destructive action |

Gold is not body text on white. White is not text on gold. Every text/background pairing in the token checks meets WCAG AA for normal text (4.5:1); state pills combine a written state and a glyph. Progress always includes a numeric percentage or byte count. Thin decorative separators need not be interaction boundaries; implementation should use the focus token for hover/focus control boundaries where a stronger 3:1 non-text boundary is required. Do not rely on a faint outline alone to identify controls.

The original navy `#182649` symbol, `#162547` wordmark, and gold `#DFAE39` remain unchanged. Use `raytone-lockup-reverse.svg` against dark navigation and `raytone-lockup-color.svg` against light navigation. The symbol-only file appears in the reference footer. SVG root contents are embedded verbatim (only the XML document declaration is omitted for HTML embedding). Never recolour paths, change their geometry, add effects, or stretch their aspect ratio. Use an Image/VectorImage source in QML rather than reconstructing the logo. Reserve at least 10 px clear space around the displayed 140 px-wide lockup.

## Typography and geometry

System stack: Inter when installed, Segoe UI, system-ui, Apple system fonts, Noto Sans CJK SC, Microsoft YaHei, sans-serif. No font download. Monospace: SFMono-Regular, Consolas, Liberation Mono, monospace. In QML resolve installed fonts using Qt font facilities and preserve platform CJK fallback; do not assume Inter is available on Omarchy.

| Role | Size / line height | Weight |
|---|---|---|
| Telemetry number | 36 / 54 px | 550 |
| Page title | 28 / 35 px | 650 |
| Featured recipe / instance | 22–24 / 31–34 px | 650 |
| Card title | 18 / 25 px | 650 |
| Navigation / subheading | 14 / 21 px | 550–650 |
| Body | 13 / 19.5 px | 400 |
| Control / data | 12 / 18 px | 400–650 |
| Caption / status | 11 / 16.5 px | 400–650 |
| Dense metadata / eyebrow | 10 / 15 px | 400–700 |

Dense 10 px metadata is secondary only. No critical action or error explanation should depend solely on it. For accessibility text scaling, increase row/card height instead of shrinking fonts. Use at least 1.5 line height for body/CJK copy; avoid fixed text baselines. Long repository names wrap at separators; retain the full value for selection/copy and accessibility. Revision uses eight SHA characters in the list and full SHA in details.

Spacing scale: 4, 8, 12, 16, 20, 24, 28, 32 px. Radius: 8 px input options, 10 px callout, 14 px card, 16 px window, 999 px pill/button/progress. Buttons are 36 px high normally and 30–32 px in dense tables; pad the input target to at least 32 px in desktop implementation. Icons are 19 px, 1.6 px stroke, built from simple paths. No shadows are necessary.

## Components and behavior

| Component | Specification |
|---|---|
| Navigation rail | Icon + label, 43 px row, 7 px gaps. Active item is gold with navy text and `current` state. Bottom hardware information is anchored. |
| Recipe card | Title, served components, memory estimate, disk estimate, source attribution, explicit state, exactly one action. Running → Stop; ready → Apply; not downloaded → Download. Downloading retains disabled Download plus percentage; conflict retains disabled Apply and explains resolution. |
| List row | Repository wraps without hiding identity; short revision, GiB, format, quantization, state, actions. Row separators span width. Run opens engine selection; unsupported engines disabled with explanation. Delete opens a confirmation naming repo, revision, reclaimable bytes, and references affected. |
| Primary button | Gold fill/navy text. One per recipe or decision area. Focus ring separate from fill. Disabled uses raised fill/muted text with an adjacent reason. |
| Secondary button | Surface fill, text colour, border. Used for Copy and Revert. Hover uses raised fill; press uses stronger outline. |
| Destructive button | Error-coloured text and border. Stop acts on the specified instance; Delete confirms snapshot removal. Never style routine Download as destructive. |
| Status pill | Rounded capsule, 4 × 9 px padding. Glyph + state text; muted for neutral, green ready, amber transitional/incomplete, red failure/conflict. “Ungated” is explicit; actual gated results use “Gated · access required”. |
| Progress | 5 px horizontal gold bar on neutral track, round ends. Show percentage and transferred/total GiB. Indeterminate state says “Resolving files…”; no invented percent. Accessible value and label update together. |
| Search | Rounded surface, leading search icon, descriptive label. Results preserve query and filters. Production uses explicit submit or debounced query, loading feedback, and offline failure recovery. |
| Filter chips | All / LLM / Video, 32 px height. Selected uses text-colour fill and inverse text, plus selected semantics. Kind classification comes from actual metadata, not model-name guesses. |
| Toast | Nonmodal bottom-right surface, maximum 360 px, 16 px padding, 10 px radius, text + status icon. “Endpoint copied” disappears after 4 seconds and announces politely; errors persist with Dismiss/Retry. Never cover the active primary action. |
| Engine chooser | Attached selection sheet/popover with engine, compatibility and availability; Run confirms selected engine. The local-model screen shows this chooser inline as a reference specimen. |
| Downloads tray | Bottom of Discover, stable height. Model, variant, byte counts, status; each download persists across navigation. Production can expand the tray for more jobs and offer Pause/Resume/Cancel. |

## Screen-specific decisions and source truth

- **Recipes:** `mockups/data/recipes.json` has one recipe, not five. Its primary card shows `running: true` over the `ready` assets state. Four smaller cards are alternate **demo state** specimens of this exact recipe. 75 GiB memory and 25 GiB disk are recipe estimates, not measured consumption. The source credit preserves Mia’s model/parser choices and the distinction that this app serves upstream vLLM with built-in MTP. “Apply” resolves conflicts before starting anything; it does not silently stop another workload.
- **Local models:** all five supplied repositories and revisions are shown. Bytes use GiB = bytes / 1,073,741,824, rounded to two decimals. Blank quantization says “Not specified”, not an inferred precision. Nemotron is incomplete with 36.2% stored, not an observed active transfer. The separate resume specimen is marked demo. Qwen3.8-Flash-Next is `complete: true` despite `incomplete: 8`; this mockup follows explicit `complete` as the supplied resolved status. Production must reconcile stale partial-file counters before running; neither disk size nor this status proves the model fits memory.
- **Discover:** all eight supplied results and all 26 variant entries are present. Result and variant lists are independently scrollable. Downloads are exact snapshot counts. Every supplied result is ungated; no gated repo is fabricated. Blank library values stay “Library not specified”; GGUF is a format, not a library. The Q4_0 size includes all four files listed by the source, including MTP and multimodal projectors. “other” remains the source’s auxiliary-file variant, not a newly named model. For a non-GGUF repository, use one “All files” selection with server-resolved size; that alternate content is not present in the supplied detail fixture.
- **Running:** served name, vLLM, port 18001, context 262,144, and ready state come from `instances.json`. The 24.6 tokens/s graph and 78.4/122 GiB values are explicitly illustrative demo telemetry; no measurements were taken. The starting row is an alternative rendering of the same instance, not another live process. The router address is the requested `http://127.0.0.1:8090/v1`; Copy copies exactly that string.
- **Agents:** all 13 agents are present. Four connectable agents show Connect/Revert and illustrative connection states. Six supported-but-not-connectable agents are grouped as supported later. Codex retains the CC Switch Responses API → chat completions note. Three unsupported agents are greyed without lowering text contrast and retain the exact source reason. Connect first previews affected configuration and backup, then applies; Revert restores the saved prior configuration.
- **Engines:** vLLM image, digest, tag and hardware validation are from the additional existing `raytone_models/engines.json` manifest. Other requested engines have no manifest entry, so image/version are “not configured / not recorded”; no fictional tag, installed state or validation is implied. “Configured” is a manifest fact, not a live container health result.

These are independent reference snapshots, not a synchronized live session. All synthetic lifecycle, connection, download and telemetry values are labeled in their own screen. Source JSON and brand files are unchanged.

## Empty, pending and error states

| Surface | Empty / pending | Failure and recovery |
|---|---|---|
| Recipes | “No recipes available” / Reload recipes | “Recipe could not be loaded” / Retry; preserve source detail. Conflict names memory, port or engine constraint; keep Apply disabled with resolution. |
| Local models | “Your model store is empty” / Discover models | Incomplete snapshot: show received/expected bytes and missing-file count; Resume or Delete. Failed deletion keeps the row and explains which files remain. |
| Discover | “Search Hugging Face for a model”; no result: “No models match these filters” / Clear filters | Offline: preserve query and cached rows, mark cache age, Retry. Gated: “Access required on Hugging Face”, with access/token flow before Download. Never claim access from an ungated fixture. |
| Download | “Preparing file list…” before total exists | “Download interrupted” with reason and Resume; disk full shows required/available storage. Preserve partial files, never show Ready before validation. |
| Running | “No models running” / Browse recipes; telemetry absent shows “— · Waiting for telemetry” | Starting keeps readiness pending; failure shows engine exit reason, View logs, Retry. Stop request becomes “Stopping…” until process exit is confirmed. |
| Agents | No compatible model: Connect disabled with “Start a compatible model first” | Configuration write failure leaves previous state intact; Revert without a backup is disabled and explained. |
| Engines | No manifest entry: “Not configured” and no invented version | Image missing, architecture mismatch and process failure are distinct. Show exact tag/digest when known and an actionable log/error. |

Empty/error messages use normal readable body text with an icon and one main recovery action. Do not represent unknown values as zero, healthy, or ready. Retain selections after recoverable errors. Return keyboard focus to the initiating control after dialog dismissal.

## Qt Quick / Quickshell mapping

This is an implementation map, not a claim that Qt code or runtime behavior was tested. Use the project's installed Quickshell/Qt APIs when implementing; no dependency/version update is implied.

| Reference element | QML construction |
|---|---|
| Application | Quickshell `FloatingWindow`, requested size 1200 × 760; root `Rectangle` background; platform/Hyprland window decoration policy determines whether the illustrated title bar is custom. Avoid duplicate title bars. |
| Shell | `RowLayout` with fixed-width rail and fill-width main `ColumnLayout`; theme singleton for tokens. |
| Logo | `Image` with `PreserveAspectFit` and original SVG file; `VectorImage` only if available in the installed Qt version. |
| Navigation | `ColumnLayout` + `Repeater`/`ItemDelegate`; text, simple SVG icon, active `Rectangle`; page state via `StackLayout` or `Loader`. |
| Cards / status | `Rectangle` + `ColumnLayout`/`RowLayout`, `Label`, explicit component state properties. |
| Models / instances / engines | `ListView` delegates or `TableView` with synchronized column widths and `ScrollBar`; do not derive row heights from character counts. |
| Search / engine picker | `TextField`, `ComboBox` or `Popup` + `ListView`; keyboard Enter/Escape and focus restoration. |
| Chips / buttons | `Button`/`ToolButton`, custom background `Rectangle`; `ButtonGroup` for kind chips; `enabled` plus readable reason. |
| Variants | `ListView` + `RadioDelegate`/`ButtonGroup`; fixed footer for size and Download; real file inclusion list available in details. |
| Progress | `ProgressBar` with rounded background/content rectangles; known numeric value or indeterminate state. |
| Telemetry | `Label`, progress control, `Repeater` of rounded vertical rectangles for the illustrative chart; real implementation binds sampled data and freshness. No chart library required. |
| Dialog / toast | Modal `Dialog` for delete/connection previews; nonmodal `Popup` and `Timer` for toast. Accessible announcement and persistent error alternative. |
| Copy | `Button` invoking the app's clipboard adapter/available Qt clipboard bridge; report success only after copy succeeds. |

Bind view models to backend state, not display strings. Key downloads by repository + revision + included-file set; key instances by instance ID. Snapshot deletion must resolve recipe/instance references. Recipe actions and model actions share the same download/run service. Preserve scroll position on refresh and avoid rebuilding all delegates for telemetry updates.

Use `Accessible.name`, role, description, and value on custom controls. Establish a predictable tab sequence: navigation → page controls → list → detail/footer. Ensure disabled-state reasons remain accessible. Provide focus rings and keyboard activation for all actions. Respect reduced motion; avoid decorative animation. Test CJK text, 125–150% system text scaling, long repos, focus restoration, and actual backend readiness before shipping.

## Verification and limits

Static checks cover 12 fixed-size windows, source repository/revision/agent/variant coverage, verbatim original SVG roots, no external resources or scripts, and WCAG AA token text contrast. No files outside `design/` are part of this change. Browser screenshot verification could not be performed: the in-app browser is unavailable and the browser security policy rejected the local file URL. Visual overflow and actual Qt/Quickshell rendering still require a permitted local browser/QML review. No download, inference, telemetry, agent configuration, or engine operation was executed by these mockups.
