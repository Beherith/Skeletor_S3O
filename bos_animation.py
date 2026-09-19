"""Pure-Python BOS animation emission for SuperSkeletor.

This module deliberately has no Blender imports.  Blender sampling belongs in the
add-on; converting already sampled frames to an include is testable plain Python.
"""

import re


BOS_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_action_name(name):
	"""Return *name* or raise ValueError when it cannot suffix a BOS function."""
	if not isinstance(name, str) or not BOS_IDENTIFIER.fullmatch(name):
		raise ValueError(
			"Action name %r is not a valid BOS identifier; use [A-Za-z_][A-Za-z0-9_]*"
			% (name,)
		)
	return name


def _number(value, brackets):
	if abs(float(value)) < 0.0000005:
		value = 0.0
	return "%s%.6f%s" % (brackets[0], float(value), brackets[1])


def _scaled(value, kind, variable_scale, variable_amplitude):
	brackets = ("[", "]") if kind == "move" else ("<", ">")
	expr = _number(value, brackets)
	if kind == "move" and variable_scale:
		expr = "((%s * MOVESCALE) / 100)" % expr
	if variable_amplitude:
		expr = "((%s * VA_amplitude) / 100)" % expr
	return expr


def _target(stance, value, kind, variable_scale, variable_amplitude):
	if not variable_amplitude:
		return _scaled(value, kind, variable_scale, False)
	# Dynamic amplitude is relative to the neutral first-frame stance.  Scaling
	# the two terms separately also keeps intermediate COB values small.
	base = _scaled(stance, kind, variable_scale, False)
	deviation = _scaled(value - stance, kind, variable_scale, True)
	return "(%s + %s)" % (base, deviation)


def render_bos_animation(
	animframes,
	action_name,
	*,
	is_walk=True,
	is_death=False,
	variable_speed=True,
	variable_scale=False,
	variable_amplitude=False,
	first_frame_stance=True,
	all_transforms_first=False,
	assimp=False,
	move_scale=1.0,
	piece_name_prefix="",
	piece_hierarchy=None,
	fps=30,
	minimum_delta=0.0001,
):
	"""Render sampled ``{frame: {piece: {channel: value}}}`` data as a BOS header.

	The include owns only ``Start<Action>`` and ``Stop<Action>``.  Walking Actions
	loop after the one-time first interval; non-walking Actions play once.
	"""
	validate_action_name(action_name)
	if float(fps) != 30.0:
		raise ValueError("Modular BOS animation export requires a 30 FPS Blender scene")
	times = sorted(animframes)
	if len(times) < 2:
		raise ValueError("Animation needs at least two distinct integer keyframes")
	if is_walk and len(times) < 3:
		raise ValueError("A looping animation needs a stance/entry frame and at least one loop frame")
	if any(not isinstance(t, int) for t in times) or any(b <= a for a, b in zip(times, times[1:])):
		raise ValueError("Animation keyframes must resolve to distinct integer Blender frames")

	axes = ["x-axis", "y-axis" if assimp else "z-axis", "z-axis" if assimp else "y-axis"]
	multipliers = {
		"move": (1.0, 1.0, 1.0),
		"turn": (1.0, 1.0, -1.0) if assimp else (-1.0, -1.0, 1.0),
	}
	start_name = "Start" + action_name
	stop_name = "Stop" + action_name
	needs_module = bool(variable_speed)
	lines = [
		"// SuperSkeletor include contract:",
		"// requires SIGNAL_MOVE and unit-owned VA_frames, VA_sleepTime, VA_amplitude,",
		"// VA_timeError, VA_useAmplitude plus variable_animation.h when Variable Speed is enabled.",
	]
	if variable_scale:
		lines.append("// requires unit-owned MOVESCALE (compile-time model calibration percentage).")
	lines.extend(["", "%s()" % start_name, "{", "\tset-signal-mask SIGNAL_MOVE;"])
	if needs_module:
		lines.extend([
			"\tVA_useAmplitude = %d;" % (1 if variable_amplitude else 0),
			"\tcall-script VA_Reset();",
		])

	stance = {}
	first = animframes[times[0]]
	if first_frame_stance:
		for piece, channels in first.items():
			for channel, value in channels.items():
				stance[(piece, channel)] = float(value)
	all_channels = {
		(piece, channel)
		for frame in animframes.values()
		for piece, values in frame.items()
		for channel in values
	}
	missing_stance = sorted(all_channels - set(stance))
	for piece, channel in missing_stance:
		lines.insert(3, "// WARNING: %s %s has no first-frame stance; amplitude/stop fallback is zero." % (piece, channel))

	exploded = set()
	piece_hierarchy = piece_hierarchy or {}

	def explode_with_children(piece, indent, result):
		if piece in exploded:
			return
		result.append("%sexplode %s%s type FALL | SMOKE | FIRE | NOHEATCLOUD;" % (indent, piece_name_prefix, piece))
		result.append("%shide %s%s;" % (indent, piece_name_prefix, piece))
		exploded.add(piece)
		for child in piece_hierarchy.get(piece, ()):
			explode_with_children(child, indent, result)

	def previous_value(frame_index, piece, channel):
		for index in range(frame_index - 1, -1, -1):
			if channel in animframes[times[index]].get(piece, {}):
				return float(animframes[times[index]][piece][channel])
		return 0.0

	def emit_interval(frame_index, indent):
		frame_time = times[frame_index]
		delta_frames = frame_time - times[frame_index - 1]
		result = []
		if needs_module:
			result.append("%scall-script VA_NextKeyframe(%d);" % (indent, delta_frames))
		result.append("%s// Blender frame %d (source delta %d)" % (indent, frame_time, delta_frames))
		frame = animframes[frame_time]
		force_all = all_transforms_first and frame_index == 1
		for piece in sorted(frame):
			if piece.startswith("PC_"):
				continue
			for channel, raw_value in sorted(frame[piece].items()):
				if channel.startswith("location"):
					kind = "move"
				elif channel in ("rot0", "rot1", "rot2"):
					kind = "turn"
				else:
					continue
				axis_index = int(channel[-1])
				value = float(raw_value) * multipliers[kind][axis_index]
				prev = previous_value(frame_index, piece, channel) * multipliers[kind][axis_index]
				if kind == "move":
					value *= float(move_scale)
					prev *= float(move_scale)
				if abs(value - prev) < minimum_delta and not force_all:
					continue
				if is_death and kind == "move" and abs(value - prev) > 100:
					explode_with_children(piece, indent, result)
					continue
				neutral = stance.get((piece, channel), 0.0) * multipliers[kind][axis_index]
				if kind == "move":
					neutral *= float(move_scale)
				speed = abs(value - prev) * 30.0
				if force_all and speed < 3.0:
					speed = max(abs(value) * 30.0, 3.0)
				target_expr = _target(neutral, value, kind, variable_scale, variable_amplitude)
				speed_expr = _scaled(speed, kind, variable_scale, variable_amplitude)
				divisor = " / VA_frames" if needs_module else " / %d" % delta_frames
				result.append(
					"%s%s %s%s to %s %s speed %s%s;"
					% (indent, kind, piece_name_prefix, piece, axes[axis_index], target_expr, speed_expr, divisor)
				)
		result.append("%ssleep %s;" % (indent, "VA_sleepTime" if needs_module else str(33 * delta_frames - 1)))
		return result

	# The first interval is an entry transition and must not become part of the loop.
	lines.extend(emit_interval(1, "\t"))
	if is_walk and len(times) > 2:
		lines.append("")
		lines.append("\twhile (TRUE) {")
		for index in range(2, len(times)):
			lines.extend(emit_interval(index, "\t\t"))
		lines.append("\t}")
	else:
		for index in range(2, len(times)):
			lines.extend(emit_interval(index, "\t"))
	lines.extend(["}", "", "%s()" % stop_name, "{"])

	# Restore every known channel.  Speeds are deliberately fixed and do not use
	# VA_frames: stopping is unit policy, not another gait interval.
	for piece, channel in sorted(all_channels):
		if piece.startswith("PC_"):
			continue
		kind = "move" if channel.startswith("location") else "turn" if channel in ("rot0", "rot1", "rot2") else None
		if kind is None:
			continue
		axis_index = int(channel[-1])
		neutral = stance.get((piece, channel), 0.0) * multipliers[kind][axis_index]
		if kind == "move":
			neutral *= float(move_scale)
		max_speed = 0.1
		for index in range(1, len(times)):
			if channel not in animframes[times[index]].get(piece, {}):
				continue
			current = float(animframes[times[index]][piece][channel])
			previous = previous_value(index, piece, channel)
			max_speed = max(max_speed, abs(current - previous) * 30.0 / (times[index] - times[index - 1]))
		if kind == "move":
			max_speed *= float(move_scale)
		lines.append(
			"\t%s %s%s to %s %s speed %s;"
			% (kind, piece_name_prefix, piece, axes[axis_index], _scaled(neutral, kind, variable_scale, False),
			   _scaled(max_speed, kind, variable_scale, False))
		)
	lines.extend(["}", ""])
	return "\n".join(lines)
