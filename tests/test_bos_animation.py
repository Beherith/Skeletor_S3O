import re
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bos_animation import render_bos_animation, sanitize_animation_name


FRAMES = {
	0: {"pelvis": {"location1": 2.0}, "thigh": {"rot0": 10.0}},
	3: {"pelvis": {"location1": 3.0}, "thigh": {"rot0": 20.0}},
	5: {"pelvis": {"location1": 4.0}, "thigh": {"rot0": 5.0}},
	9: {"pelvis": {"location1": 2.5}, "thigh": {"rot0": 10.0}},
}


def render(name="Walk", **options):
	return render_bos_animation(FRAMES, name, source_path=r"N:\animations\unit.blend", **options)


@pytest.mark.parametrize(
	("raw", "expected"),
	[
		(None, "Walk"),
		("", "Walk"),
		("Run_2", "Run_2"),
		("Fast Walk", "Fast_Walk"),
		("Two  Steps!", "Two__Steps_"),
		("2 Leg Walk", "_2_Leg_Walk"),
		("Wälk", "W_lk"),
	],
)
def test_animation_name_sanitization_preserves_each_character(raw, expected):
	assert sanitize_animation_name(raw) == expected


def test_walk_header_is_directly_includeable_and_fully_namespaced():
	output = render("Fast Walk", variable_speed=True, variable_amplitude=True, variable_scale=True)
	assert "ANIMATIONNAME" not in output
	assert "Fast_Walk() {//Created by" in output
	assert "STOP_Fast_Walk() {" in output
	assert "#ifndef Fast_Walk_DEFAULT_ANIM_TIME" in output
	assert "#ifndef Fast_Walk_MIN_SPEED_PERCENT" in output
	assert "#ifndef Fast_Walk_MAX_SPEED_PERCENT" in output
	assert "#ifndef Fast_Walk_MOVESCALE" in output
	assert "#ifndef Fast_Walk_SIGNAL_MASK" in output
	assert "#ifndef Fast_Walk_FIRST_FRAME_COUNT" in output
	assert "#ifndef Fast_Walk_STOP_SPEED" in output
	assert "#ifndef Fast_Walk_INIT" in output
	assert "#ifndef Fast_Walk_CALC_DESIRED_FRAMES_AMPLITUDE" in output
	for forbidden in ("StartMoving", "StopMoving", "static-var isMoving, maxSpeed;"):
		assert forbidden not in "\n".join(
			line for line in output.splitlines() if not line.startswith("//")
		)


def test_template_comments_and_source_path_are_preserved():
	output = render(variable_speed=True, variable_amplitude=True)
	assert "This header file should be directly #included into the target unit script." in output
	assert "These two static-var's MUST be declared in the script that includes this header." in output
	assert "Times here are specified as milliseconds per frame. So 33 is the default speed." in output
	assert "Controls the lowest speed percentage for the animation" in output
	assert "responsible for blending move speeds and and animation amplitude" in output
	assert "The first frame of the walking animation MUST be done at at most 2x the desired frames." in output
	assert "COB angular constants being 182" in output
	assert "Moves have a linear constant of 64K" in output
	assert "get PRINT (get (GAME_FRAME), Walk_currentPercent" in output
	assert "Call-script this when you want to stop the animation" in output
	assert r"N:\animations\unit.blend" in output
	assert "//delta=" not in output


def test_combined_speed_amplitude_macro_keeps_fractional_time_and_clamps_frames():
	output = render(variable_speed=True, variable_amplitude=True)
	assert "Walk_currentPercent = ((100 * get (CURRENT_SPEED)) / maxSpeed - 100);" in output
	assert "Walk_currentTime = (Walk_DEFAULT_ANIM_TIME * (100 - (Walk_currentPercent / 2))) / 100;" in output
	assert "Walk_amplitude = 100 + ((Walk_currentPercent * 60) / 100);" in output
	assert "Walk_remainder_ms = Walk_currentTime % 33;" in output
	assert "if (Walk_desiredFrames < 1) Walk_desiredFrames = 1;" in output
	assignments = re.findall(r"^[ \t]*Walk_desiredFrames = (\d+);", output, re.MULTILINE)
	assert [int(value) for value in assignments] == [3, 2, 4]


def test_speed_only_uses_lean_inverse_speed_macro_and_three_locals():
	output = render(variable_speed=True, variable_amplitude=False)
	assert "#ifndef Walk_MIN_ANIM_TIME" in output
	assert "#define Walk_MIN_ANIM_TIME (Walk_DEFAULT_ANIM_TIME/2)" in output
	assert "#ifndef Walk_MAX_ANIM_TIME" in output
	assert "#define Walk_MAX_ANIM_TIME (Walk_DEFAULT_ANIM_TIME*3)" in output
	assert "#ifndef Walk_CALC_DESIRED_FRAMES" in output
	assert "Walk_currentTime = Walk_DEFAULT_ANIM_TIME * maxSpeed / (get (CURRENT_SPEED) + 1);" in output
	assert "if (Walk_currentTime < Walk_MIN_ANIM_TIME) Walk_currentTime = Walk_MIN_ANIM_TIME;" in output
	assert "if (Walk_currentTime > Walk_MAX_ANIM_TIME) Walk_currentTime = Walk_MAX_ANIM_TIME;" in output
	assert "Walk_remainder_ms = Walk_currentTime % 33;" in output
	assert "if (Walk_desiredFrames < 1) Walk_desiredFrames = 1;" in output
	assert "Walk_CALC_DESIRED_FRAMES_AMPLITUDE" not in output
	assert "Walk_MIN_SPEED_PERCENT" not in output
	assert "Walk_MAX_SPEED_PERCENT" not in output
	assert "Walk_currentPercent" not in output
	assert "Walk_amplitude" not in output
	local_vars = re.findall(r"^\tvar (Walk_[A-Za-z0-9_]+);", output, re.MULTILINE)
	assert local_vars == ["Walk_remainder_ms", "Walk_currentTime", "Walk_desiredFrames"]


def test_first_transition_count_is_a_conditional_override():
	output = render(variable_speed=True, variable_amplitude=True)
	calc = output.index("\t\tWalk_CALC_DESIRED_FRAMES_AMPLITUDE();")
	guard = output.index("#ifdef Walk_FIRST_FRAME_COUNT")
	override = output.index("Walk_desiredFrames = Walk_FIRST_FRAME_COUNT;")
	assert calc < guard < override


def test_amplitude_scales_absolute_targets_and_runtime_speed():
	output = render(variable_speed=True, variable_amplitude=True, variable_scale=True)
	commands = "\n".join(line for line in output.splitlines() if line.lstrip().startswith(("move ", "turn ")))
	assert "([3.000000] * Walk_MOVESCALE)" in commands
	assert "[1.000000]" not in commands  # no stance-relative deviation
	assert "(<-20.000000> * Walk_amplitude) / 100" in commands
	assert "(<300.000000> / 100) * Walk_amplitude" in commands


def test_stop_speed_override_applies_to_moves_and_turns():
	output = render(variable_speed=True, variable_amplitude=True, variable_scale=True)
	stop = output.split("STOP_Walk()", 1)[1]
	move_line = next(line for line in stop.splitlines() if line.lstrip().startswith("move "))
	turn_line = next(line for line in stop.splitlines() if line.lstrip().startswith("turn "))
	assert "Walk_STOP_SPEED" in move_line
	assert "Walk_STOP_SPEED" in turn_line


@pytest.mark.parametrize(
	("variable_speed", "variable_amplitude", "uses_current_speed", "scales_commands"),
	[
		(False, False, False, False),
		(True, False, True, False),
		(False, True, True, True),
		(True, True, True, True),
	],
)
def test_walk_speed_amplitude_option_matrix(variable_speed, variable_amplitude, uses_current_speed, scales_commands):
	output = render(variable_speed=variable_speed, variable_amplitude=variable_amplitude)
	assert ("get (CURRENT_SPEED)" in output) is uses_current_speed
	commands = "\n".join(line for line in output.splitlines() if line.lstrip().startswith(("move ", "turn ")))
	assert ("Walk_amplitude" in commands) is scales_commands
	if variable_amplitude:
		assert "Walk_CALC_DESIRED_FRAMES_AMPLITUDE()" in output
	else:
		assert "Walk_CALC_DESIRED_FRAMES()" in output


@pytest.mark.parametrize("is_death", [False, True])
def test_standstill_animation_has_adjustable_fixed_timing_without_unit_speed(is_death):
	output = render(
		"Idle" if not is_death else "Death",
		is_walk=False,
		is_death=is_death,
		variable_speed=True,
		variable_amplitude=True,
	)
	name = "Death" if is_death else "Idle"
	assert "#ifndef %s_DEFAULT_ANIM_TIME" % name in output
	assert "%s_CALC_DESIRED_FRAMES()" % name in output
	assert "%s_currentTime = %s_desiredFrames * %s_DEFAULT_ANIM_TIME" % (name, name, name) in output
	for forbidden in ("CURRENT_SPEED", "MAX_SPEED", "maxSpeed", "isMoving", "%s_amplitude" % name):
		assert forbidden not in output


def test_first_frame_stance_off_restores_zero():
	output = render(variable_speed=True, variable_amplitude=True, first_frame_stance=False)
	stop = output.split("STOP_Walk()", 1)[1]
	assert "[0.000000]" in stop
	assert "<0.000000>" in stop


def test_empty_name_uses_walk_namespace():
	output = render_bos_animation(FRAMES, "", variable_speed=True)
	assert "Walk()" in output
	assert "STOP_Walk()" in output


def test_source_fps_is_explicitly_30():
	with pytest.raises(ValueError, match="30 FPS"):
		render_bos_animation(FRAMES, "Walk", fps=24)


def test_death_action_keeps_recursive_piece_explosion_in_named_entry_point():
	frames = {
		0: {"body": {"location0": 0.0}, "arm": {"location0": 0.0}},
		3: {"body": {"location0": 101.0}, "arm": {"location0": 0.0}},
	}
	output = render_bos_animation(
		frames,
		"Big Death",
		is_walk=False,
		is_death=True,
		variable_speed=True,
		variable_amplitude=True,
		piece_hierarchy={"body": ["arm"]},
	)
	assert "Big_Death()" in output
	assert "STOP_Big_Death()" in output
	assert "explode body type" in output
	assert "explode arm type" in output
	assert "CURRENT_SPEED" not in output
