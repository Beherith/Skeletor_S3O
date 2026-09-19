import re
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bos_animation import render_bos_animation, validate_action_name


FRAMES = {
	0: {"pelvis": {"location1": 2.0}, "thigh": {"rot0": 10.0}},
	3: {"pelvis": {"location1": 3.0}, "thigh": {"rot0": 20.0}},
	5: {"pelvis": {"location1": 4.0}, "thigh": {"rot0": 5.0}},
	9: {"pelvis": {"location1": 2.5}, "thigh": {"rot0": 10.0}},
}


def render(**options):
	return render_bos_animation(FRAMES, "Walk", **options)


def test_uneven_variable_animation_is_include_ready():
	output = render(variable_speed=True, variable_amplitude=True)
	declarations = re.findall(r"^([A-Za-z_]\w*)\(\)\s*$", output, re.MULTILINE)
	assert declarations == ["StartWalk", "StopWalk"]
	assert [int(value) for value in re.findall(r"VA_NextKeyframe\((\d+)\)", output)] == [3, 2, 4]
	assert output.index("VA_NextKeyframe(3)") < output.index("turn thigh")
	assert output.count("sleep VA_sleepTime;") == 3
	for forbidden in ("static-var", "UnitSpeed", "StartMoving", "StopMoving", "isMoving"):
		assert forbidden not in output
	assert "while (TRUE)" in output
	assert output.index("VA_NextKeyframe(3)") < output.index("while (TRUE)")


@pytest.mark.parametrize(
	("variable_speed", "variable_amplitude", "has_call", "uses_amplitude"),
	[
		(False, False, False, False),
		(True, False, True, False),
		(True, True, True, True),
		(False, True, False, True),
	],
)
def test_speed_amplitude_option_matrix(variable_speed, variable_amplitude, has_call, uses_amplitude):
	output = render(variable_speed=variable_speed, variable_amplitude=variable_amplitude)
	assert ("VA_NextKeyframe" in output) is has_call
	commands = "\n".join(line for line in output.splitlines() if line.lstrip().startswith(("move ", "turn ")))
	assert ("VA_amplitude" in commands) is uses_amplitude
	if variable_speed:
		assert ("VA_useAmplitude = 1" in output) is variable_amplitude
	else:
		assert "sleep 98;" in output
		assert "sleep 65;" in output
		assert "sleep 131;" in output


def test_dynamic_amplitude_is_stance_relative_and_scale_composes():
	output = render(variable_speed=True, variable_amplitude=True, variable_scale=True)
	assert "MOVESCALE" in output
	assert "[2.000000]" in output  # neutral pelvis stance
	assert "[1.000000]" in output  # first deviation, rather than scaling absolute 3
	assert "<-10.000000>" in output  # neutral non-zero thigh angle after BOS axis conversion


def test_first_frame_stance_off_restores_zero():
	output = render(variable_speed=True, variable_amplitude=True, first_frame_stance=False)
	stop = output.split("StopWalk()", 1)[1]
	assert "[0.000000]" in stop
	assert "<0.000000>" in stop


@pytest.mark.parametrize("name", ["Walk", "Run_2", "_Idle"])
def test_valid_action_names(name):
	assert validate_action_name(name) == name


@pytest.mark.parametrize("name", ["", "Two Words", "2Run", "Walk-Left", "A/B"])
def test_invalid_action_names(name):
	with pytest.raises(ValueError, match="valid BOS identifier"):
		validate_action_name(name)


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
		"Death",
		is_walk=False,
		is_death=True,
		variable_speed=False,
		piece_hierarchy={"body": ["arm"]},
	)
	assert "StartDeath()" in output
	assert "StopDeath()" in output
	assert "explode body type" in output
	assert "explode arm type" in output
