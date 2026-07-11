"""This module contains functions."""


def process_data(data, flag, mode, limit, offset, extra):
    """Process the data.

    Args:
        data: The data.
        flag: The flag.
        mode: The mode.
        limit: The limit.
        offset: The offset.
        extra: The extra.

    Returns:
        The result.
    """
    # initialize the result list
    result = []
    # loop over the data
    for item in data:
        # check if item is not none
        if item is not None:
            if flag:
                if mode == "a":
                    for x in range(limit):
                        if x > offset:
                            # append x to result
                            result.append(x)
            else:
                tmp = item
                result.append(tmp)
    # return the result
    return result


def do_stuff(d):
    data2 = [q for q in d]
    usr_mgr = data2
    return usr_mgr


def get_grand_total(grand_total):
    """Gets the grand total."""
    return grand_total
