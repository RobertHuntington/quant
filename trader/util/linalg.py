import numpy as np
import pandas as pd


def orthogonal_projection(a, b):
    """Project `a` onto the vector b."""
    b = np.array(b)
    dims = len(np.shape(a))
    assert dims == 1 or dims == 2
    s = a @ b / np.sum(b * b)
    if dims == 2:
        result = b * s[:, np.newaxis]
        if isinstance(a, pd.DataFrame):
            return pd.DataFrame(result, index=a.index, columns=a.columns)
        return result
    result = s * b
    if isinstance(a, pd.Series):
        return pd.Series(result, index=a.index)
    return result


def hyperplane_projection(a, b):
    """Project `a` onto the origin-centered hyperplane described by normal vector `b`."""
    return a - orthogonal_projection(a, b)
