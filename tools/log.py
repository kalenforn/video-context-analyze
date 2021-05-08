import os

def write_log(message: str, file_: str = 'error.log'):

    message += '\n'
    if not os.path.exists(file_):
        with open(file_, 'w') as f:
            f.write(message)
    else:
        with open(file_, 'a') as f:
            f.write(message)
