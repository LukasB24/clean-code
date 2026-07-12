from pandas import DataFrame
def random_function():
    ac = 0
    bc = 5 # number assignment
    df = DataFrame({'a': [1, 2, 3], 'b': [4, 5, 6]}) # create a DataFrame

    for i in range(10):
        ac += 1
        bc -= 1
        for j in range(5):
            ac += 1 # increase a number
            bc -= 1 # decrease the variable
            for k in range(3): # iterate three times
                ac += 1
                bc -= 1
    return ac, bc