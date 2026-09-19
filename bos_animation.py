"""Pure-Python BOS animation emission for SuperSkeletor.

Blender sampling belongs in the add-on. This module turns already sampled
frames into a directly include-able, per-animation BOS header.
"""

import re


BOS_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def sanitize_animation_name(name):
	"""Return a BOS-safe name while preserving one output character per input.

	An absent name becomes ``Walk``. Invalid characters are replaced one for
	one with underscores; a leading digit is retained and prefixed with an
	underscore.
	"""
	if not isinstance(name, str) or not name:
		return "Walk"
	cleaned = "".join(
		ch if (ch.isascii() and (ch.isalpha() or ch.isdigit() or ch == "_")) else "_"
		for ch in name
	)
	if cleaned[0].isdigit():
		cleaned = "_" + cleaned
	return cleaned


def validate_action_name(name):
	"""Compatibility helper returning the normalized BOS animation name."""
	return sanitize_animation_name(name)


def _number(value, brackets):
	if abs(float(value)) < 0.0000005:
		value = 0.0
	return "%s%.6f%s" % (brackets[0], float(value), brackets[1])


def _runtime_target(value, kind, namespace, variable_scale, variable_amplitude):
	brackets = ("[", "]") if kind == "move" else ("<", ">")
	expr = _number(value, brackets)
	if kind == "move" and variable_scale and variable_amplitude:
		return "(((%s * %s_MOVESCALE) / 10000) * %s_amplitude)" % (expr, namespace, namespace)
	if kind == "move" and variable_scale:
		return "((%s * %s_MOVESCALE) / 100)" % (expr, namespace)
	if variable_amplitude:
		# COB angle constants have much less precision than linear constants. Do
		# the division after multiplying turn targets so sub-degree values survive.
		return "((%s * %s_amplitude) / 100)" % (expr, namespace)
	return expr


def _runtime_speed(value, kind, namespace, variable_scale, variable_amplitude):
	brackets = ("[", "]") if kind == "move" else ("<", ">")
	expr = _number(value, brackets)
	if kind == "move" and variable_scale and variable_amplitude:
		return "(((%s * %s_MOVESCALE) / 10000) * %s_amplitude)" % (expr, namespace, namespace)
	if kind == "move" and variable_scale:
		return "((%s * %s_MOVESCALE) / 100)" % (expr, namespace)
	if variable_amplitude:
		return "((%s / 100) * %s_amplitude)" % (expr, namespace)
	return expr


def _append_common_configuration(lines, namespace, *, is_walk, uses_unit_speed, variable_speed,
								 variable_amplitude, variable_scale):
	lines.extend([
		"// Times here are specified as milliseconds per frame. So 33 is the default speed.",
		"// If you want to accelerate or decelerate the animation, adjust this accordingly.",
		"// Best results are always with the default baked animation time of 33, so consider remastering the animation if it differs significantly.",
		"#ifndef %s_DEFAULT_ANIM_TIME" % namespace,
		"\t#define %s_DEFAULT_ANIM_TIME 33" % namespace,
		"#endif",
		"",
	])

	if uses_unit_speed:
		lines.extend([
			"// Controls the lowest speed percentage for the animation, given as a fraction of mastered speed",
			"#ifndef %s_MIN_SPEED_PERCENT" % namespace,
			"\t#define %s_MIN_SPEED_PERCENT 33" % namespace,
			"#endif",
			"",
			"// Controls the highest speed percentage for the animation, given as a fraction of mastered speed",
			"#ifndef %s_MAX_SPEED_PERCENT" % namespace,
			"\t#define %s_MAX_SPEED_PERCENT 175" % namespace,
			"#endif",
			"",
		])

	if variable_scale:
		lines.extend([
			"// This is a hard-coded scaling factor affecting moves only that is only needed if the model is ever upscaled (turns are unaffected by model scaling)",
			"#ifndef %s_MOVESCALE" % namespace,
			"\t#define %s_MOVESCALE 100" % namespace,
			"#endif",
			"",
		])

	lines.extend([
		"// The default signal mask is just movement. Please ensure that you change it if you want the animation to be interruptible by other signals.",
		"#ifndef %s_SIGNAL_MASK" % namespace,
		"\t#define %s_SIGNAL_MASK SIGNAL_MOVE" % namespace,
		"#endif",
		"",
	])

	if is_walk:
		lines.extend([
			"// The canonical way to override the duration of the first frame (e.g. from stance to walk loop) is by setting this count.",
			"#ifndef %s_FIRST_FRAME_COUNT" % namespace,
			"\t#define %s_FIRST_FRAME_COUNT 3" % namespace,
			"#endif",
			"",
		])

	lines.extend([
		"// The speed at which the stop animation should play, expressed in realative percent of the mastering",
		"#ifndef %s_STOP_SPEED" % namespace,
		"\t#define %s_STOP_SPEED 100" % namespace,
		"#endif",
		"",
	])

	if uses_unit_speed:
		lines.extend([
			"// Call this from Create(), this is the quick initializer that ensure maxSpeed is set and has a minimum value of 1.",
			"#ifndef %s_INIT" % namespace,
			"\t#define %s_INIT()\\" % namespace,
			"\t\tmaxSpeed = get (MAX_SPEED); \\",
			"\t\tif (maxSpeed < 1) maxSpeed = 1;",
			"#endif",
			"",
			"// The following macro is used only within the script itself, and is responsible for blending move speeds and and animation amplitude",
			"// Along with keeping track of fractional milliseconds of animation time needed.",
			"#ifndef %s_CALC_DESIRED_FRAMES_AMPLITUDE" % namespace,
			"\t#define %s_CALC_DESIRED_FRAMES_AMPLITUDE() \\" % namespace,
			"\t\t%s_currentPercent = ((100 * get (CURRENT_SPEED)) / maxSpeed - 100); \\" % namespace,
			"\t\tif (%s_currentPercent < %s_MIN_SPEED_PERCENT - 100) %s_currentPercent = %s_MIN_SPEED_PERCENT - 100; \\" % (namespace, namespace, namespace, namespace),
			"\t\tif (%s_currentPercent > %s_MAX_SPEED_PERCENT - 100) %s_currentPercent = %s_MAX_SPEED_PERCENT - 100; \\" % (namespace, namespace, namespace, namespace),
		])
		if variable_speed:
			lines.append("\t\t%s_currentTime = (%s_DEFAULT_ANIM_TIME * (100 - (%s_currentPercent / 2))) / 100; \\" % (namespace, namespace, namespace))
		else:
			lines.append("\t\t%s_currentTime = %s_DEFAULT_ANIM_TIME; \\" % (namespace, namespace))
		if variable_amplitude:
			lines.append("\t\t%s_amplitude = 100 + ((%s_currentPercent * 60) / 100); \\" % (namespace, namespace))
		else:
			lines.append("\t\t%s_amplitude = 100; \\" % namespace)
		lines.extend([
			"\t\t%s_currentTime = %s_desiredFrames * %s_currentTime + %s_remainder_ms; \\" % (namespace, namespace, namespace, namespace),
			"\t\t%s_remainder_ms = %s_currentTime %% 33; \\" % (namespace, namespace),
			"\t\t%s_desiredFrames = %s_currentTime / 33; \\" % (namespace, namespace),
			"\t\tif (%s_desiredFrames < 1) %s_desiredFrames = 1;" % (namespace, namespace),
			"#endif",
			"//get PRINT (get (GAME_FRAME), %s_currentPercent, %s_currentTime, %s_amplitude);" % (namespace, namespace, namespace),
			"",
		])
	else:
		lines.extend([
			"// The following macro is used only within the script itself, and keeps track of fractional milliseconds of animation time needed.",
			"// It does not depend on unit speed, so it is suitable for idle and death animations.",
			"#ifndef %s_CALC_DESIRED_FRAMES" % namespace,
			"\t#define %s_CALC_DESIRED_FRAMES() \\" % namespace,
			"\t\t%s_currentTime = %s_desiredFrames * %s_DEFAULT_ANIM_TIME + %s_remainder_ms; \\" % (namespace, namespace, namespace, namespace),
			"\t\t%s_remainder_ms = %s_currentTime %% 33; \\" % (namespace, namespace),
			"\t\t%s_desiredFrames = %s_currentTime / 33; \\" % (namespace, namespace),
			"\t\tif (%s_desiredFrames < 1) %s_desiredFrames = 1;" % (namespace, namespace),
			"#endif",
			"",
		])


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
	source_path="",
):
	"""Render sampled ``{frame: {piece: {channel: value}}}`` data as a BOS header."""
	namespace = sanitize_animation_name(action_name)
	if not BOS_IDENTIFIER.fullmatch(namespace):
		raise ValueError("Unable to make a valid BOS identifier from %r" % (action_name,))
	if float(fps) != 30.0:
		raise ValueError("BOS animation export requires a 30 FPS Blender scene")
	times = sorted(animframes)
	if len(times) < 2:
		raise ValueError("Animation needs at least two distinct integer keyframes")
	if is_walk and len(times) < 3:
		raise ValueError("A looping animation needs a stance/entry frame and at least one loop frame")
	if any(not isinstance(t, int) for t in times) or any(b <= a for a, b in zip(times, times[1:])):
		raise ValueError("Animation keyframes must resolve to distinct integer Blender frames")

	# Standstill animations must never read CURRENT_SPEED. Walk options remain
	# independent: speed can alter cadence, amplitude, both, or neither.
	variable_speed = bool(is_walk and variable_speed)
	variable_amplitude = bool(is_walk and variable_amplitude)
	uses_unit_speed = variable_speed or variable_amplitude
	variable_scale = bool(variable_scale)

	axes = ["x-axis", "y-axis" if assimp else "z-axis", "z-axis" if assimp else "y-axis"]
	multipliers = {
		"move": (1.0, 1.0, 1.0),
		"turn": (1.0, 1.0, -1.0) if assimp else (-1.0, -1.0, 1.0),
	}
	lines = [
		"// This is an animation header generated by SuperSkeletor for the file %s" % (source_path or "..."),
		"// This header file should be directly #included into the target unit script.",
		"",
	]
	if is_walk and uses_unit_speed:
		lines.extend([
			"// These two static-var's MUST be declared in the script that includes this header.",
			"// static-var isMoving, maxSpeed;",
			"",
			"// Im uncertain if the isMoving is really needed, but it doesnt cost much and it works.",
			"",
		])
	elif is_walk:
		lines.extend([
			"// This static-var MUST be declared in the script that includes this header.",
			"// static-var isMoving;",
			"",
		])
	lines.extend([
		"// The animation function's name gets exported as %s, e.g. WALK" % namespace,
		"",
	])
	_append_common_configuration(
		lines,
		namespace,
		is_walk=is_walk,
		uses_unit_speed=uses_unit_speed,
		variable_speed=variable_speed,
		variable_amplitude=variable_amplitude,
		variable_scale=variable_scale,
	)

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
	for piece, channel in sorted(all_channels - set(stance)):
		lines.append("// WARNING: %s %s has no first-frame stance; stop fallback is zero." % (piece, channel))
	if all_channels - set(stance):
		lines.append("")

	piece_hierarchy = piece_hierarchy or {}
	exploded = set()

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

	calc_macro = "%s_CALC_DESIRED_FRAMES_AMPLITUDE" % namespace if uses_unit_speed else "%s_CALC_DESIRED_FRAMES" % namespace

	def emit_interval(frame_index, indent, first_interval=False):
		frame_time = times[frame_index]
		delta_frames = frame_time - times[frame_index - 1]
		result = [
			"%s%s_desiredFrames = %d;" % (indent, namespace, delta_frames),
			"%s%s();" % (indent, calc_macro),
		]
		if first_interval and is_walk:
			result.extend([
				"#ifdef %s_FIRST_FRAME_COUNT" % namespace,
				"%s%s_desiredFrames = %s_FIRST_FRAME_COUNT;" % (indent, namespace, namespace),
				"%sif (%s_desiredFrames < 1) %s_desiredFrames = 1;" % (indent, namespace, namespace),
				"#endif",
				"%s// Note that due to COB angular constants being 182, <1> == 182 in integers, putting the division by 100 only makes sense on speed terms, which are much larger. On the turn axis targets, constant folding would truncate our small, less than <1> angles" % indent,
				"%s// Moves have a linear constant of 64K, so there we can safely put the division by 100 before the mults with amplitude." % indent,
			])
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
				speed = abs(value - prev) * 30.0
				if force_all and speed < 3.0:
					speed = max(abs(value) * 30.0, 3.0)
				target_expr = _runtime_target(value, kind, namespace, variable_scale, variable_amplitude)
				speed_expr = _runtime_speed(speed, kind, namespace, variable_scale, variable_amplitude)
				result.append(
					"%s%s %s%s to %s %s speed %s / %s_desiredFrames;"
					% (indent, kind, piece_name_prefix, piece, axes[axis_index], target_expr, speed_expr, namespace)
				)
		result.append("%ssleep ((33 * %s_desiredFrames) - 1);" % (indent, namespace))
		return result

	lines.extend([
		"// Start-script %s(); usually in StartMoving()" % namespace,
		"%s() {//Created by https://github.com/Beherith/Skeletor_S3O from %s" % (namespace, source_path or "..."),
		"\tset-signal-mask %s_SIGNAL_MASK;" % namespace,
		"\tvar %s_remainder_ms;" % namespace,
		"\tvar %s_currentTime;" % namespace,
	])
	if uses_unit_speed:
		lines.append("\tvar %s_currentPercent;" % namespace)
	lines.append("\tvar %s_desiredFrames;" % namespace)
	if uses_unit_speed:
		lines.append("\tvar %s_amplitude; // Always expressed in percent." % namespace)
		lines.append("\t//%s_remainder_ms = RAND(0, 66); // Could make sense to randomize by 1 or 2 frames, but hardly noticeable anyway." % namespace)
	lines.append("")

	if is_walk:
		lines.append("\tif (isMoving) { // The first frame of the walking animation MUST be done at at most 2x the desired frames.")
		lines.extend(emit_interval(1, "\t\t", first_interval=True))
		lines.extend(["\t}", "\twhile (isMoving) {"])
		for index in range(2, len(times)):
			lines.append("\t\tif (isMoving) { //Frame:%d" % times[index])
			lines.extend(emit_interval(index, "\t\t\t"))
			lines.append("\t\t}")
		lines.append("\t}")
	else:
		for index in range(1, len(times)):
			lines.append("\t// Frame:%d" % times[index])
			lines.extend(emit_interval(index, "\t", first_interval=index == 1))
	lines.extend(["}", ""])

	stop_name = "STOP_" + namespace
	lines.extend([
		"// Call-script this when you want to stop the animation",
		"// This is generated by collecting the maximum speeds during the animation, so it is dependant on the setup, but should still be adjustable via %s_STOP_SPEED" % namespace,
		"%s() {" % stop_name,
	])
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
		if kind == "move" and variable_scale:
			target_expr = "((%s * %s_MOVESCALE) / 100)" % (_number(neutral, ("[", "]")), namespace)
			speed_expr = "((((%s * %s_MOVESCALE) / 100) * %s_STOP_SPEED) / 100)" % (
				_number(max_speed, ("[", "]")), namespace, namespace
			)
		else:
			target_expr = _number(neutral, ("[", "]") if kind == "move" else ("<", ">"))
			speed_expr = _number(max_speed, ("[", "]") if kind == "move" else ("<", ">"))
			speed_expr = "((%s / 100) * %s_STOP_SPEED)" % (speed_expr, namespace)
		lines.append(
			"\t%s %s%s to %s %s speed %s;"
			% (kind, piece_name_prefix, piece, axes[axis_index], target_expr, speed_expr)
		)
	lines.extend(["}", ""])
	return "\n".join(lines)
