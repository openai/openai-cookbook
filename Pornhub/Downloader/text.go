package utils

import "bytes"

func Censor(in string, pad string, chars int, front bool) string {
	b := bytes.Buffer{}
	for i := 0; i < chars; i++ {
		if i < len(in) {
			b.WriteString(string(pad[0]))
		}
	}

	if len(in) > chars {
		if front {
			return b.String() + in[chars-1:]
		}
		return in[0:len(in)-(chars-1)] + b.String()
	}
	return b.String()
}

func Truncate(in string, chars, mode int) string {
	if chars >= len(in) {
		return in
	}

	half := chars / 2
	if mode < 1 {
		// front
		return "..." + in[len(in)-(chars):]
	} else if mode == 1 {
		// mid
		return in[:half] + "..." + in[len(in)-(half):]
	} else {
		// back
		return in[:chars] + "..."
	}
}
