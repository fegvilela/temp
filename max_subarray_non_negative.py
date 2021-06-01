"""Problem Description

Given an array of integers, A of length N, find out the maximum sum sub-array of non negative numbers from A.

The sub-array should be contiguous i.e., a sub-array created by choosing the second and fourth element and skipping the third element is invalid.

Maximum sub-array is defined in terms of the sum of the elements in the sub-array.

Find and return the required subarray.

NOTE:

If there is a tie, then compare with segment's length and return segment which has maximum length.
If there is still a tie, then return the segment with minimum starting index.

I'm gonna need the following variables that will hold the value according to its given description

NOTE: I WILL CHECK THE END OF A SUB-ARRAY, NOT THE BEGINNING

***** I will access: *****
- CURRENT_ELEMET_VALUE ----> It will hold the value of the element currently being analyzed on that iteration - I will check wheter it is a positive or a negative and do the max accordingly;

- CURRENT_ELEMENT_INDEX ----> It will hold the index value of the element currently being analyzed on that iteration. Positive indexes.
***** I will hold: *****

CURRENT_SUM ----> This variable will hold the current sum of the sequential positive array values in that iteration; NOTE: THIS VARIABLE WILL BE ASSIGNED AS SOON AS I ANALYZE WHETER THE NUMBER IS POSITIVE OR NOT AND IF IT'S SEQUENTIAL.

LAST_SUM ----> This variable will be equal to zero until I find a negative number. Given the possibility of encountering several different sequences of positive numbers, I need to store the biggest sum as I'm encountering them so I can compare then each time a find a negative number; NOTE> THIS VARIABLE WILL BE ASSIGNED AS SOON AS I ENCOUNTER A NEGATIVE NUMBER, THAT IS BECAUSE I NEED TO HOLD THE CURRENT_SUM VARIABLE FOR FURTHER COMPARISON AND THUS I WILL ZERO THE CURRENT_SUM VARIABLE SO I CAN RESTART SUMMING.

===== So far, I can only calculate the maximum sum sub-array of non negatives in an array that has no ties. Plus, I can't tell the indexes of those elements making up the biggest sum; So in order to get rid of a tie, I need to not only store the elements indexes and their respective values, but I have to compare the length of each segment which will only be possible if I'm aware of the number of indexes that make up that sub-array =====

**** I will hold a list containing a dictionary describing each positive sub-array *****

SUB_ARRAY_LENGTH_COUNTER ----> In order to compare various sub-arrays, I need to set a counter counting the sub-array elements so I can use it in the METADATA variable

METADATA ----> The list will be made of using the following standard


"""

A = [1, 1, 1, 1, 1, 5, -3, -7, 2, 3, 5, -2, 3, 3, 1, 3]


def sub_array_parser(array):
    current_sum = 0
    biggest_sum = 0
    current_sub_array_length = 0
    biggest_sub_array_length = 0
    current_sub_array_starting_index = -1
    biggest_sub_array_staring_index = -1
    searching_for_sub_array = True

    print(array)

    for index, value in enumerate(array, start=0):
        if value >= 0 and searching_for_sub_array:
            searching_for_sub_array = False
            current_sub_array_starting_index = index

        if value >= 0:
            current_sum += value
            current_sub_array_length += 1

            if current_sum > biggest_sum:
                biggest_sum = current_sum
                biggest_sub_array_length = current_sub_array_length
                biggest_sub_array_staring_index = current_sub_array_starting_index


            elif current_sum == biggest_sum:
                if current_sub_array_length > biggest_sub_array_length:
                    biggest_sub_array_length = current_sub_array_length
                    biggest_sub_array_staring_index = current_sub_array_starting_index

        else:
            current_sum = 0
            current_sub_array_length = 0
            searching_for_sub_array = True

        # print(f'current sum: {current_sum} | biggest sum: {biggest_sum} | current starting index: {current_sub_array_starting_index} | biggest starting index: {biggest_sub_array_staring_index} | current sub array length: {current_sub_array_length} | biggest sub array length: {biggest_sub_array_length}')
    
    return (array[biggest_sub_array_staring_index:biggest_sub_array_staring_index + biggest_sub_array_length])

biggest_sub_array = sub_array_parser(A)

print(biggest_sub_array)
