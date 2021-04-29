import pprint as ppt

def screen_array(
    array, 
    factors=None,
    limit=1024,
    odd_only=False,
    even_only=False,
    factors_mutually_exclusive=True
    ):

    result_set = list()

    if factors is not None:
        non_factors = list()
        if factors_mutually_exclusive:
            for factor in factors:
                for index in range(len(array)):
                    if ((array[index] % factor) != 0) and (index not in non_factors):
                        non_factors.append(index)
            
            non_factors.sort(reverse=True)
            for index in non_factors:
                array.pop(index)
        else:
            failers = list()
            for index in range(len(array)):
                number = array[index]
                is_failer = True
                for factor in factors:
                    if (number % factor == 0):
                        is_failer = False
                
                if is_failer:
                    failers.append(index)
            
            failers.sort(reverse=True)

            for index in failers:
                array.pop(index)

    ppt.pprint(array)

    for number in array:
        if (number <= limit):
            if odd_only:
                if (number % 2 >= 1):
                    result_set.append(number)

            elif even_only:
                if (number % 2 == 0):
                    result_set.append(number)
            else:
                result_set.append(number)

    return {"Result Set:":result_set, "Elements:":len(result_set)}

one_to_forty = list(range(1, 41))

ppt.pprint(
    screen_array(
        array=one_to_forty,
        factors=[4, 3],
        factors_mutually_exclusive=False
    )
)