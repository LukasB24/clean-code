def calc(u, o):
    if u.active:
        if o.total > 500:
            discount = o.total * 0.15
        else:
            discount = o.total * 0.05
    try:
        charge(o, o.total - discount)
    except:
        pass
    return discount
