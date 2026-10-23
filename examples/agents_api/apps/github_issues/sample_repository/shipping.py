def shipping_cost(subtotal: float, *, express: bool = False) -> float:
    if subtotal >= 100:
        return 0
    if express:
        return 15
    return 7
