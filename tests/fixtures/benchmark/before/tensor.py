def transform(x, idx, i):
    out = x[:, None, idx[i + 1]:idx[i + 2]:2, ::-1]
    val1 = x[i][0][-1]
    return out, val1
