def confusion_matrix(inferred, groundtruth):
    assert len(inferred) == len(groundtruth)
    confusion = {
        'True': {'True': 0, 'False': 0, 'NEE': 0},
        'False': {'True': 0, 'False': 0, 'NEE': 0},
        'NEE': {'True': 0, 'False': 0, 'NEE': 0},
    }
    for i, g in zip(inferred, groundtruth):
        confusion[i][g] += 1

    # Pretty print the confusion matrix
    print('\tGroundtruth')
    print('\tTrue\tFalse\tNEE')
    for i in confusion:
        print(i, end='\t')
        for g in confusion[i]:
            print(confusion[i][g], end='\t')
        print()

    return confusion