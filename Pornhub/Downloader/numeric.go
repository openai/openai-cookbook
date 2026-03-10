package utils

import "golang.org/x/exp/constraints"

type Number interface {
	constraints.Integer | constraints.Float
}

func NumberMin[T Number](val1, val2 T) T {
	if val1 < val2 {
		return val1
	}
	return val2
}

func NumberMax[T Number](val1, val2 T) T {
	if val1 > val2 {
		return val1
	}
	return val2
}
