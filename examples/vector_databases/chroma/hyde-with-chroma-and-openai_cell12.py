def get_groundtruth(evidence):
    groundtruth = []
    for e in evidence:
        # Evidence is empty 
        if len(e) == 0:
            groundtruth.append('NEE')
        else:
            # In this dataset, all evidence for a given claim is consistent, either SUPPORT or CONTRADICT
            if list(e.values())[0][0]['label'] == 'SUPPORT':
                groundtruth.append('True')
            else:
                groundtruth.append('False')
    return groundtruth