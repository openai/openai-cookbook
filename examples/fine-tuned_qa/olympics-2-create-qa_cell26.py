def expand_lists(out):
    """
    Expand a pandas series containing lists into a series, where each list element becomes a value on its own

    Input is a row per paragraph, which has multiple questions
    Output is a row per question
    """
    cols = [pd.DataFrame(out[name].tolist()).stack().reset_index(level=1, drop=True).rename(name) for name in out.columns] 
    return pd.concat(cols, axis=1)

out_expanded = expand_lists(out)
out_expanded['rank'] = out_expanded.ada.apply(lambda x: x[0] if x != [] else -2)
out_expanded['tokens'] = out_expanded.ada.apply(lambda x: x[1] if x != [] else -2)
