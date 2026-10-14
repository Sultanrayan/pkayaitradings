"""Static checks on the Zenmux frontend.

The backend has thorough tests; these cover the properties that exist only in the
client and that a type-checker will not catch:

* ``/zenmux`` and ``/ai`` must not share persisted state, or a probability lands in
  the assistant's history and is replayed as a prior turn.
* No machine-learning vocabulary may reach the screen. The product requirement is
  explicit that the user never sees XGBoost, LightGBM, thresholds or backend names,
  and none of that is enforced by the type system.
* The API key must never appear in client code or a ``NEXT_PUBLIC_`` variable.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"
ZENMUX_DIR = FRONTEND_SRC / "components" / "zenmux"
VIEW = ZENMUX_DIR / "zenmux-view.tsx"
CARD = ZENMUX_DIR / "analysis-card.tsx"
COMPOSER = ZENMUX_DIR / "composer.tsx"
LIST = ZENMUX_DIR / "conversation-list.tsx"
CONSTANTS = ZENMUX_DIR / "constants.ts"
AI_VIEW = FRONTEND_SRC / "components" / "ai" / "ai-view.tsx"
API_TS = FRONTEND_SRC / "lib" / "api.ts"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


#: Vocabulary that must never appear anywhere in the Zenmux UI source. Checked
#: across every file the screen renders, not just the ones that format text.
FORBIDDEN = (
    "xgboost",
    "lightgbm",
    "light gbm",
    "n_features",
    "n_rows_built",
    "decision threshold",
)


# --------------------------------------------------------------------------- #
# No machine-learning vocabulary in the UI
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("filename", ["zenmux-view.tsx", "analysis-card.tsx", "composer.tsx", "constants.ts"])
def test_no_jargon_in_zenmux_client_code(filename: str) -> None:
    """A stray identifier in a component is one refactor away from the screen."""
    lowered = _source(ZENMUX_DIR / filename).lower()
    for word in FORBIDDEN:
        assert word not in lowered, f"{word!r} present in {filename}"


def test_no_jargon_in_the_rendered_copy() -> None:
    """String literals are what a reader actually sees."""
    for path in (VIEW, CARD, COMPOSER, CONSTANTS, LIST):
        for literal in re.findall(r'"([^"\\]{4,})"', _source(path)):
            lowered = literal.lower()
            for word in FORBIDDEN:
                assert word not in lowered, f"{word!r} in a literal in {path.name}: {literal!r}"


def test_the_api_client_does_not_expose_a_backend_field() -> None:
    """The response type is the contract; a backend field would render somewhere."""
    source = _source(API_TS)
    zenmux_block = source.split("export interface ZenmuxAnalysis {")[1].split("\n}")[0]
    for banned in ("backend", "threshold", "n_rows_built", "trees"):
        assert banned not in zenmux_block


def test_the_request_sends_a_model_slug_not_a_backend() -> None:
    source = _source(API_TS)
    zenmux_block = source.split("zenmux: (input: {")[1].split("zenmuxModels")[0]
    assert "model?: ZenmuxModelId" in zenmux_block
    assert "backend" not in zenmux_block


def test_the_view_sends_the_selected_model() -> None:
    source = _source(VIEW)
    assert "api.zenmux({" in source
    assert "model," in source


# --------------------------------------------------------------------------- #
# Model selector
# --------------------------------------------------------------------------- #


def test_only_two_models_are_offered() -> None:
    source = _source(CONSTANTS)
    assert '"super"' in source
    assert '"flash"' in source
    assert source.count('name: "') == 2


def test_the_model_names_and_descriptions_match_the_spec() -> None:
    source = _source(CONSTANTS)
    assert "Super Zenmux" in source
    assert "Deep market analysis" in source
    assert "Flash Zenmux" in source
    assert "Fast market analysis" in source


def test_the_default_model_is_super() -> None:
    assert 'DEFAULT_ZENMUX_MODEL: ZenmuxModelId = "super"' in _source(CONSTANTS)
    assert "DEFAULT_ZENMUX_MODEL" in _source(VIEW)


def test_the_selector_offers_a_name_and_a_description() -> None:
    """The two models must be distinguishable by purpose, per the requirement."""
    source = _source(COMPOSER)
    assert "entry.name" in source
    assert "entry.description" in source


def test_the_composer_shows_the_symbol_as_fixed_context() -> None:
    """XAU/USD is the only instrument the service covers, so it is a label not a control."""
    source = _source(COMPOSER)
    assert "ZENMUX_SYMBOL_LABEL" in source
    assert "ZENMUX_TIMEFRAMES" in source


def test_the_composer_has_an_enter_control() -> None:
    source = _source(COMPOSER)
    assert '"Send"' in source
    assert "CornerDownLeft" in source


# --------------------------------------------------------------------------- #
# No microphone, no free typing
# --------------------------------------------------------------------------- #


def test_the_microphone_is_gone() -> None:
    """Voice input was removed at the user's request; nothing may remain of it.

    Checked against rendered strings rather than whole files: a comment explaining why
    the composer has no microphone is legitimate documentation, and banning the word
    outright would forbid exactly the note that stops someone re-adding one.
    """
    for path in (COMPOSER, VIEW, CONSTANTS):
        source = _source(path)
        assert "Mic" not in source, f"microphone icon left in {path.name}"
        assert "speech" not in source.lower(), f"speech logic left in {path.name}"
        offenders = [text for text in _rendered_strings(path) if "voice" in text.lower()]
        assert not offenders, f"voice copy left in {path.name}: {offenders}"


def test_the_speech_hook_was_removed() -> None:
    """Orphaned once the microphone went; shipping it would be dead code."""
    assert not (ZENMUX_DIR / "use-speech-recognition.ts").exists()


def test_nothing_references_the_browser_speech_api() -> None:
    for path in sorted(ZENMUX_DIR.rglob("*.ts*")):
        source = _source(path)
        assert "SpeechRecognition" not in source, f"speech API left in {path.name}"


def test_the_composer_has_no_text_input() -> None:
    """The requirement is that typing is impossible, not merely discouraged.

    Leaving a text field on a screen nobody types into reads as the primary control
    and sends people to the wrong place, so the whole field is gone rather than
    disabled.

    ``PromptInput`` may appear in the doc comment explaining why this component is not
    that component; what must not exist is the import or the JSX usage.
    """
    source = _source(COMPOSER)
    assert "<textarea" not in source
    assert "<input" not in source
    assert "contentEditable" not in source
    assert "<PromptInput" not in source
    assert "from \"@/components/ui/ai-chat-input\"" not in source


def test_the_view_renders_no_free_text_control() -> None:
    source = _source(VIEW)
    assert "<textarea" not in source
    assert "<input" not in source


def test_the_view_no_longer_shows_the_empty_state_prompt_cards() -> None:
    """The 'Analyze the latest XAU/USD market' box and its siblings are gone."""
    source = _source(VIEW)
    assert "EXAMPLE_PROMPTS" not in source
    for prompt in (
        "Analyze the latest XAU/USD market",
        "What is the current market trend?",
        "Find key support and resistance levels",
        "Give me a market outlook",
    ):
        assert prompt not in source, f"{prompt!r} still rendered in the empty state"


def test_the_empty_state_copy_survives() -> None:
    """Only the prompt cards were removed, not the branding."""
    source = _source(VIEW)
    assert "Ask Zenmux about XAU/USD" in source
    assert "AI-powered market analysis for Gold." in source


# --------------------------------------------------------------------------- #
# Phrase box
# --------------------------------------------------------------------------- #


def test_a_phrase_box_sits_beside_the_model_selector() -> None:
    source = _source(COMPOSER)
    assert 'aria-label="Phrases"' in source
    assert "Phrases" in source
    # The model picker must come before the phrase box for it to read as "near".
    assert source.index('aria-label="AI model"') < source.index('aria-label="Phrases"')


def test_the_phrase_box_lists_speakable_phrases() -> None:
    assert "SPEAKABLE_PHRASES.map" in _source(COMPOSER)
    source = _source(CONSTANTS)
    assert "SPEAKABLE_PHRASES: string[]" in source
    assert source.count('",\n') >= 8, "expected a real phrase library"


def test_the_phrases_are_written_to_be_spoken() -> None:
    """They replace a keyboard prompt library, so they must be sayable sentences.

    Asserted on shape rather than exact copy: a question or a statement, never a
    bare button label. ``"Give me a market summary."`` is perfectly speakable, so
    requiring a question mark would reject a good phrase for the wrong reason.
    """
    block = _source(CONSTANTS).split("SPEAKABLE_PHRASES: string[] = [")[1].split("];")[0]
    phrases = [line.strip().strip(",").strip('"') for line in block.splitlines() if line.strip()]
    assert len(phrases) >= 8
    for phrase in phrases:
        assert phrase.endswith(("?", ".")), f"not a spoken sentence: {phrase!r}"
        assert len(phrase.split()) >= 4, f"too terse to speak naturally: {phrase!r}"


def test_tapping_a_phrase_starts_listening() -> None:
    """With no keyboard entry the phrases are the only route to a question."""
    source = _source(COMPOSER)
    phrase_click = source.split('aria-label="Phrases"')[1]
    assert "handlePhraseClick(phrase)" in phrase_click


def test_the_phrase_box_explains_itself() -> None:
    source = _source(COMPOSER)
    assert "Tap a phrase, or select a word inside one" in source


# --------------------------------------------------------------------------- #
# Selecting a word inside a phrase
# --------------------------------------------------------------------------- #


def test_phrases_allow_text_selection() -> None:
    """Without select-text the browser collapses the drag and no word can be picked."""
    source = _source(COMPOSER)
    assert "select-text" in source


def test_selection_is_captured_on_mouse_up() -> None:
    """Mouse-up precedes click, so the selection is known by the time click runs."""
    source = _source(COMPOSER)
    assert "onMouseUp={() => handlePhraseMouseUp(phrase)}" in source
    assert "onClick={() => handlePhraseClick(phrase)}" in source
    assert "window.getSelection()" in source


def test_a_selected_word_replaces_the_whole_phrase() -> None:
    """The headline requirement: select a word, and that word becomes the text."""
    source = _source(COMPOSER)
    assert "captured.phrase === phrase ? captured.text : phrase" in source


def test_a_selection_from_another_phrase_is_not_reused() -> None:
    """A selection left in phrase A must not be applied when phrase B is tapped."""
    source = _source(COMPOSER)
    assert "selectionRef.current = null" in source
    assert "captured && captured.phrase === phrase" in source


def test_a_selection_spanning_two_phrases_is_rejected() -> None:
    """It belongs to neither phrase, so it must fall back to the whole phrase."""
    source = _source(COMPOSER)
    assert "phrase.includes(selected)" in source


def test_the_browser_selection_is_cleared_after_staging() -> None:
    """Otherwise the next tap reads the previous selection."""
    source = _source(COMPOSER)
    assert "removeAllRanges()" in source


# --------------------------------------------------------------------------- #
# The typing reveal
# --------------------------------------------------------------------------- #


def test_the_text_is_revealed_progressively() -> None:
    """It must not appear all at once."""
    source = _source(COMPOSER)
    assert "setInterval" in source
    assert "revealed: current.revealed + 1" in source
    assert "staged.text.slice(0, revealed)" in source


def test_the_reveal_shows_a_caret_while_running() -> None:
    source = _source(COMPOSER)
    assert "revealed < staged.text.length" in source
    assert "bg-foreground" in source


def test_the_reveal_speed_is_bounded() -> None:
    """Fixed per-character timing makes a long phrase crawl.

    The delay is derived from the phrase length against a total budget, so short and
    long phrases both finish in about a second.
    """
    source = _source(COMPOSER)
    assert "REVEAL_BUDGET_MS = 1100" in source
    assert "REVEAL_MIN_DELAY_MS = 8" in source
    assert "REVEAL_MAX_DELAY_MS = 20" in source
    assert "revealDelay(stagedText.length)" in source
    assert "Math.min(REVEAL_MAX_DELAY_MS" in source
    assert "Math.max(REVEAL_MIN_DELAY_MS" in source


def test_the_reveal_scrolls_to_follow_the_newest_character() -> None:
    source = _source(COMPOSER)
    assert "overflow-x-auto" in source
    assert "scrollLeft = element.scrollWidth" in source


def test_the_reveal_is_announced_to_screen_readers() -> None:
    source = _source(COMPOSER)
    assert 'aria-live="polite"' in source
    assert 'role="status"' in source


def test_reduced_motion_is_honoured() -> None:
    """Animating regardless of the preference is an accessibility failure."""
    source = _source(COMPOSER)
    assert "prefers-reduced-motion: reduce" in source
    assert "reducedMotion ? text.length : 0" in source


def test_the_resting_text_is_the_hint_not_a_voice_prompt() -> None:
    source = _source(COMPOSER)
    assert "COMPOSER_HINT" in source
    assert 'COMPOSER_HINT = "Ask about XAU/USD."' in _source(CONSTANTS)


# --------------------------------------------------------------------------- #
# Sending is explicit
# --------------------------------------------------------------------------- #


def test_nothing_is_sent_automatically() -> None:
    """Staging a phrase is not consent to send it.

    The only path to a request must be the Enter button, so no effect, timer or
    selection handler may reach ``onSubmit``.
    """
    source = _source(COMPOSER)
    assert source.count("onSubmit(") == 1, "onSubmit must be called from exactly one place"
    assert "handleSend" in source

    # Isolate the send handler precisely. Splitting on the first `};` would run past
    # it into unrelated code and produce a false positive.
    send_block = source.split("const handleSend", 1)[1]
    send_block = send_block.split("}, [staged, busy, onSubmit]);", 1)[0]
    assert "onSubmit(text)" in send_block
    for trigger in ("useEffect", "setTimeout", "setInterval", "onMouseUp", "onClick"):
        assert trigger not in send_block, f"{trigger} must not appear in the send path"


def test_enter_sends_and_clears_the_staged_text() -> None:
    source = _source(COMPOSER)
    assert "onSubmit(text);" in source
    assert "setStaged(null)" in source


def test_enter_is_gated_on_staged_text_and_readiness() -> None:
    source = _source(COMPOSER)
    assert "const canSend = Boolean(staged?.text.trim()) && !busy" in source
    assert "disabled={!canSend}" in source


def test_enter_sits_after_the_text_on_the_right() -> None:
    """The requirement is an Enter control on the right of the staged text."""
    source = _source(COMPOSER)
    enter_at = source.index('aria-label="Send"')
    text_at = source.index("overflow-x-auto")
    assert enter_at > text_at, "Enter must render after the text area"

    # Same row, so the button cannot have drifted onto the context row above.
    row = source.split('<div className="flex items-center gap-3 border-t border-border', 1)[1]
    assert row.index("overflow-x-auto") < row.index('aria-label="Send"')


def test_the_text_area_still_takes_the_slack() -> None:
    """The button is fixed-width, so the text must absorb the remaining space.

    With the button last, a text element that did not flex would leave the row
    ragged and the send control stranded away from the edge.
    """
    source = _source(COMPOSER)
    assert "min-w-0 flex-1" in source.split("overflow-x-auto", 1)[0]

    # The Enter button's own class list, taken from just after its label.
    button_block = source.split('aria-label="Send"', 1)[1].split(">", 1)[0]
    assert "shrink-0" in button_block, "the Enter button must not grow"
    assert "size-9" in button_block, "the Enter button must keep its fixed size"


def test_the_view_submits_only_what_the_composer_sends() -> None:
    source = _source(VIEW)
    assert "onSubmit={(text) => void submit(text)}" in source
    assert source.count("submit(") == 1, "only the composer may start a request"


# --------------------------------------------------------------------------- #
# Empty state, quick actions and example prompts
# --------------------------------------------------------------------------- #


def test_the_empty_state_copy_matches_the_spec() -> None:
    source = _source(VIEW)
    assert "Ask Zenmux about XAU/USD" in source
    assert "AI-powered market analysis for Gold." in source


def test_the_four_quick_action_pills_are_gone() -> None:
    """Removed so the phrase box is the screen's only prompt library.

    Two overlapping lists of things to ask, in the same small area above the
    composer, is clutter that makes both harder to scan.
    """
    assert "QUICK_ACTIONS" not in _source(CONSTANTS)
    assert "QUICK_ACTIONS" not in _source(VIEW)
    for label in ("Analyze Market", "Market Trend", "Key Levels", "Market Summary"):
        assert label not in _source(VIEW), f"the {label!r} pill is still rendered"


def test_the_four_example_prompts_are_gone_from_the_constants() -> None:
    """Replaced by SPEAKABLE_PHRASES, which the composer actually offers."""
    source = _source(CONSTANTS)
    assert "EXAMPLE_PROMPTS" not in source
    for prompt in (
        "Analyze the latest XAU/USD market",
        "What is the current market trend?",
        "Find key support and resistance levels",
        "Give me a market outlook",
    ):
        assert prompt not in source, f"{prompt!r} still defined"


def test_the_composer_is_the_only_way_to_ask() -> None:
    """With the pills gone, the phrase box and Enter are the whole input surface.

    Asserted by counting call sites: the handler is defined as ``submit = useCallback``
    and invoked exactly once, from the composer. A second invocation would mean
    another control that can start a request behind the user's back.
    """
    source = _source(VIEW)
    assert "onSubmit={(text) => void submit(text)}" in source
    assert source.count("submit(") == 1, "only the composer may start a request"
    assert "const submit = useCallback" in source


# --------------------------------------------------------------------------- #
# Card fields
# --------------------------------------------------------------------------- #


def test_the_card_renders_every_required_field() -> None:
    source = _source(CARD)
    for field in (
        "model_name",
        "symbol_label",
        "timeframe",
        "Confidence",
        "Market structure",
        "Why",
        "Support",
        "Resistance",
        "Updated",
    ):
        assert field in source, f"card is missing {field!r}"


def test_the_card_labels_the_source_of_each_reason() -> None:
    """Direction comes from the classifier, structure from indicators.

    Without this the card implies one model produced all of it, which overstates
    what the classifier does.
    """
    source = _source(CARD)
    assert "SOURCE_LABEL" in source
    assert 'analysis: "From price action"' in source
    assert 'model: "From the model"' in source
    assert "SOURCE_LABEL[reason.source]" in source


def test_the_card_shows_a_reduced_state_when_history_is_short() -> None:
    source = _source(CARD)
    assert "analysis.limited" in source


def test_the_card_does_not_inflate_confidence() -> None:
    """Confidence is |p-0.5|*2 and typically 0.05-0.25; it must print as-is."""
    source = _source(CARD)
    assert "Math.round(analysis.confidence * 100)" in source
    assert "* 200" not in source
    assert "* 100 +" not in source


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #


def test_the_three_date_groups_are_defined_in_order() -> None:
    source = _source(CONSTANTS)
    assert 'GROUP_ORDER: ConversationGroup[] = ["Today", "Yesterday", "Previous 7 days"]' in source


def test_grouping_is_calendar_based() -> None:
    """A conversation from 23:50 yesterday belongs with yesterday's work."""
    source = _source(CONSTANTS)
    assert "setHours(0, 0, 0, 0)" in source


def test_conversations_older_than_seven_days_are_not_listed() -> None:
    source = _source(LIST)
    assert "groupFor(conversation.createdAt)" in source
    assert "if (!group) continue" in source


def test_conversations_can_be_selected_renamed_and_deleted() -> None:
    source = _source(LIST)
    assert "onSelect" in source
    assert "onRename" in source
    assert "onDelete" in source
    assert "Rename" in source
    assert "Delete" in source


def test_the_sidebar_keeps_the_new_chat_button() -> None:
    assert "New Chat" in _source(VIEW)


def test_titles_are_shortened_for_the_sidebar() -> None:
    source = _source(CONSTANTS)
    assert "titleFrom" in source
    assert "slice(0, 34)" in source


# --------------------------------------------------------------------------- #
# Failure reporting
# --------------------------------------------------------------------------- #


def test_the_server_reason_is_actually_read() -> None:
    """Regression: every real reason was being discarded.

    ``request()`` throws ``ApiError(detail, status)`` — the server's wording lands in
    ``message``. This handler used to read ``error.detail``, which does not exist on
    that class, so the specific cause could never surface and the generic apology
    always won.
    """
    source = _source(VIEW)
    assert "error instanceof ApiError" in source
    assert "error.message?.trim()" in source
    assert "error.status" in source


def test_the_view_imports_the_error_class_it_branches_on() -> None:
    """Without the import the instanceof check narrows to never and silently fails."""
    assert "ApiError" in _source(VIEW).split("from \"@/lib/api\"")[0]


def test_a_transport_failure_is_distinguished_from_an_application_error() -> None:
    """A dead backend produces a TypeError with no status and no server wording.

    Reporting that as an application error sends the user to retry a request that
    cannot succeed, so it gets its own copy naming the likely cause.
    """
    source = _source(VIEW)
    assert "error instanceof TypeError" in source
    assert "Check that the API is running" in source


def test_no_failure_claims_the_service_is_unreachable() -> None:
    """The old wording asserted a cause it could not know.

    "Could not reach the analysis service" is wrong for a 503 caused by a missing
    API key, and it fires on every application error because the real reason was
    never read. Only the transport branch may claim unreachability.
    """
    source = _source(VIEW)
    body = source.split("function errorMessage", 1)[1].split("\n}", 1)[0]
    reach_claims = len(re.findall(r"could not reach", body, re.IGNORECASE))
    assert reach_claims == 1, (
        f"only the transport branch may claim unreachability, found {reach_claims}"
    )
    assert "Could not reach the analysis service" in body
    # The last-resort branch must not assert a cause at all.
    fallback = body.rsplit("return", 1)[1]
    assert "unreachable" not in fallback
    assert "reach" not in fallback


def test_every_failure_branch_produces_something() -> None:
    source = _source(VIEW)
    body = source.split("function errorMessage", 1)[1].split("\n}", 1)[0]
    for branch in ("ApiError", "TypeError"):
        assert branch in body
    assert body.count("return") >= 4, "each shape needs its own message"


def test_a_failed_request_renders_a_message_but_no_card() -> None:
    """The card is attached only on success, so a failure cannot render a half card."""
    source = _source(VIEW)
    success_block = source.split("const result = await api.zenmux", 1)[1].split("} catch", 1)[0]
    assert "analysis: result" in success_block
    catch_block = source.split("} catch (error) {", 1)[1].split("} finally", 1)[0]
    assert "analysis" not in catch_block, "a failure must not attach a partial card"


# --------------------------------------------------------------------------- #
# Separation from /ai
# --------------------------------------------------------------------------- #


def test_the_two_surfaces_do_not_share_a_storage_key() -> None:
    """Sharing one key would cross-contaminate both histories.

    The bug this prevents is subtle: a Zenmux card stored under the AI key would be
    read back by ``/ai`` as a prior assistant turn and sent to the language model as
    conversation context.
    """
    zenmux_key = re.search(r'const STORAGE_KEY = "([^"]+)"', _source(VIEW))
    ai_key = re.search(r'const STORAGE_KEY = "([^"]+)"', _source(AI_VIEW))

    assert zenmux_key and ai_key, "both views must declare a storage key"
    assert zenmux_key.group(1) != ai_key.group(1)
    assert zenmux_key.group(1).startswith("pkay.zenmux")


def test_zenmux_does_not_import_the_ai_view() -> None:
    source = _source(VIEW)
    assert "ai-view" not in source
    assert "@/components/ai/" not in source


def test_zenmux_does_not_reuse_the_shared_composer() -> None:
    """``ai-chat-input`` belongs to /ai; reusing it would couple the two screens."""
    source = _source(VIEW)
    assert "ai-chat-input" not in source
    assert "PromptInput" not in source


def test_zenmux_calls_its_own_api_method() -> None:
    assert "api.zenmux(" in _source(VIEW)
    assert "api.chat(" not in _source(VIEW)


def test_the_two_routes_are_distinct_files() -> None:
    zenmux_page = FRONTEND_SRC / "app" / "(app)" / "zenmux" / "page.tsx"
    ai_page = FRONTEND_SRC / "app" / "(app)" / "ai" / "page.tsx"
    assert zenmux_page.exists()
    assert ai_page.exists()
    assert zenmux_page.read_text(encoding="utf-8") != ai_page.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Credential handling
# --------------------------------------------------------------------------- #


def test_the_api_key_is_never_present_in_frontend_source() -> None:
    """A ``sk-...`` literal in client code would ship the credential to browsers.

    Checked across the whole frontend tree, because the key could plausibly be
    pasted into a shared module.
    """
    offenders: list[str] = []
    for path in FRONTEND_SRC.rglob("*.ts*"):
        if re.search(r"\bsk-[A-Za-z0-9]{16,}", _source(path)):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, f"credential-shaped string in frontend source: {offenders}"


def test_server_side_zenmux_env_is_not_exposed_publicly() -> None:
    """Anything ``NEXT_PUBLIC_`` is inlined into the client bundle at build time."""
    offenders: list[str] = []
    for path in FRONTEND_SRC.rglob("*.ts*"):
        for line in _source(path).splitlines():
            if "ZENMUX" in line and "NEXT_PUBLIC" in line:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {line.strip()}")
    assert not offenders, f"server-side Zenmux config exposed publicly: {offenders}"


def test_the_api_client_does_not_send_a_key_header() -> None:
    source = _source(API_TS)
    zenmux_block = source.split("zenmux: (input: {")[1].split("zenmuxModels")[0]
    assert "Authorization" not in zenmux_block
    assert "sk-" not in zenmux_block


# --------------------------------------------------------------------------- #
# Scope guards — the requirement excludes trading controls
# --------------------------------------------------------------------------- #


def _rendered_strings(path: Path) -> list[str]:
    """Quoted literals and bare JSX text — the parts a reader can actually see.

    Comments and Tailwind class names are excluded deliberately: scanning whole
    files for a word like "order" matches ``border`` in a class attribute and
    "in display order" in a comment, neither of which is a trading control.

    Only double-quoted literals are read, matching this codebase's formatting. A
    single-quote pattern would run across apostrophes in prose comments.
    """
    source = _source(path)
    literals = re.findall(r'"([^"\\\n]{3,})"', source)
    jsx_text = re.findall(r">([^<>{}\n]{3,})<", source)
    return [*literals, *jsx_text]


@pytest.mark.parametrize(
    "word", ["order", "position size", "buy now", "sell now", "place order", "execute"]
)
def test_no_trading_execution_controls(word: str) -> None:
    """This screen is analysis only; no order or execution affordance belongs here."""
    pattern = re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE)
    for path in (VIEW, CARD, COMPOSER, CONSTANTS, LIST):
        offenders = [text for text in _rendered_strings(path) if pattern.search(text)]
        assert not offenders, f"{word!r} rendered in {path.name}: {offenders}"


@pytest.mark.parametrize(
    "phrase", ["guaranteed", "risk-free", "sure thing", "can't lose", "risk free"]
)
def test_no_outcome_is_promised(phrase: str) -> None:
    """A ROC-AUC near 0.52 cannot support a certainty claim."""
    for path in (VIEW, CARD, COMPOSER, CONSTANTS):
        offenders = [text for text in _rendered_strings(path) if phrase in text.lower()]
        assert not offenders, f"{phrase!r} rendered in {path.name}: {offenders}"


# --------------------------------------------------------------------------- #
# Navbar and symbol handling
# --------------------------------------------------------------------------- #


def test_the_navbar_links_to_zenmux() -> None:
    navbar = _source(FRONTEND_SRC / "components" / "navbar" / "index.tsx")
    assert 'href: "/zenmux"' in navbar
    assert 'label: "Zenmux"' in navbar


def test_the_navbar_still_links_to_the_existing_pages() -> None:
    navbar = _source(FRONTEND_SRC / "components" / "navbar" / "index.tsx")
    for href in ("/signals", "/news", "/market"):
        assert f'href: "{href}"' in navbar


def test_the_navbar_marks_the_active_route() -> None:
    """Requirement: highlight Zenmux as the active page."""
    navbar = _source(FRONTEND_SRC / "components" / "navbar" / "index.tsx")
    assert "pathname.startsWith(link.href)" in navbar


def test_zenmux_pins_xauusd_and_offers_a_timeframe() -> None:
    source = _source(API_TS)
    zenmux_block = source.split("zenmux: (input: {")[1].split("zenmuxModels")[0]
    assert '"XAUUSD"' in zenmux_block
    assert "timeframe?: ZenmuxTimeframe" in zenmux_block


# --------------------------------------------------------------------------- #
# Full-height layout
# --------------------------------------------------------------------------- #


def test_zenmux_is_a_fullscreen_route() -> None:
    """The gap bug: without this the page gets the padded document layout.

    ``AppShell`` renders ``main`` with ``px-4 pb-16 pt-20`` and no height for
    non-fullscreen routes. The Zenmux root asks for ``h-full``, which resolves to
    ``auto`` against an auto-height parent, so those paddings became visible dead
    space at the top and bottom with the sidebar inset from the window edge, and the
    composer was never pinned to the bottom.
    """
    shell = _source(FRONTEND_SRC / "components" / "app-shell.tsx")
    assert '"/zenmux"' in shell


def test_ai_and_dashboard_remain_fullscreen() -> None:
    shell = _source(FRONTEND_SRC / "components" / "app-shell.tsx")
    for route in ("/dashboard", "/ai"):
        assert f'"{route}"' in shell, f"{route} lost its fullscreen layout"


def test_the_zenmux_view_asks_to_fill_its_parent() -> None:
    """``h-full`` is only meaningful once the parent has a definite height."""
    assert 'className="flex h-full flex-col pt-14"' in _source(VIEW)


def test_the_thread_scrolls_and_the_composer_is_its_own_bottom_band() -> None:
    """Composer sits at the bottom because the thread above it takes the slack."""
    source = _source(VIEW)
    assert "min-h-0 flex-1 overflow-y-auto" in source, "thread must be the scrolling region"
    assert "border-t border-border" in source, "composer must be a separate bottom band"


# --------------------------------------------------------------------------- #
# Timeframe control
# --------------------------------------------------------------------------- #


def test_only_m5_and_m15_are_offered() -> None:
    """H1 and beyond have too little history behind them to read honestly."""
    source = _source(CONSTANTS)
    assert 'ZENMUX_TIMEFRAMES: ZenmuxTimeframe[] = ["M5", "M15"]' in source


def test_the_default_timeframe_is_m5() -> None:
    assert 'DEFAULT_ZENMUX_TIMEFRAME: ZenmuxTimeframe = "M5"' in _source(CONSTANTS)


def test_the_composer_offers_a_timeframe_picker() -> None:
    source = _source(COMPOSER)
    assert 'aria-label="Timeframe"' in source
    assert "ZENMUX_TIMEFRAMES.map" in source


def test_the_view_forwards_the_selected_timeframe() -> None:
    source = _source(VIEW)
    assert "timeframe," in source
    assert "onTimeframeChange={setTimeframe}" in source


def test_the_api_client_no_longer_hardcodes_m5() -> None:
    """The timeframe is the caller's choice now, not a constant in the client."""
    source = _source(API_TS)
    zenmux_block = source.split("zenmux: (input: {")[1].split("zenmuxModels")[0]
    assert 'timeframe?: ZenmuxTimeframe' in zenmux_block
    assert '"M5"' not in zenmux_block


def test_the_card_discloses_the_classifier_timeframe_when_it_differs() -> None:
    """An M15 card must not present an M5 probability as though it were M15."""
    source = _source(CARD)
    assert "model_timeframe" in source
    assert "model_timeframe !== analysis.timeframe" in source


# --------------------------------------------------------------------------- #
# Composer input behaviour
# --------------------------------------------------------------------------- #


def test_the_composer_does_not_dim_while_busy() -> None:
    """The composer must not grey out; only Enter is gated."""
    assert "opacity-60" not in _source(COMPOSER)


def test_context_controls_stay_live_while_busy() -> None:
    """Changing the model or timeframe mid-request is harmless, so nothing disables them.

    Only Enter is gated — the four popovers are always interactive, which keeps a
    queued question configurable while the previous one is still running.
    """
    source = _source(COMPOSER)
    assert "disabled={!canSend}" in source
    # No other button in the composer may carry a disabled binding.
    assert source.count("disabled=") == 1


def test_the_view_does_not_read_the_btc_capable_market_context() -> None:
    """The shared symbol provider offers BTCUSD, which cannot be scored."""
    assert "useMarketContext" not in _source(VIEW)
