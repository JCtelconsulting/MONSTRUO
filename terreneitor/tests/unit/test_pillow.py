try:
    from PIL import Image  # noqa: F401

    print("Pillow OK")
except ImportError as e:
    print(f"Pillow FAIL: {e}")
