import gc


def clean_memory(func):

    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        del args, kwargs
        gc.collect()
        return result

    return wrapper
