import json

def load_json(file_path: str) -> dict:
    """
    Load json file.
    :param file_path: absolute file path.
    :return: a dict.
    """
    with open(file_path, 'r') as f:
        result = json.load(f)

    return result

convert_2_json = lambda x: json.dumps(x)
