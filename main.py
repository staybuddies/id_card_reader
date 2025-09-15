import pytesseract
from PIL import Image, ImageEnhance, ImageFilter

def preprocess_image(image_path):
    try:
        img = Image.open(image_path).convert('L')
        print("Image loaded and converted to grayscale.")

        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2.0)
        print("Contrast enhanced.")

        img = img.filter(ImageFilter.SHARPEN)
        print("Image sharpened.")

        threshold = 128
        img = img.point(lambda p: p > threshold and 255)
        print("Image binarized.")

        return img

    except FileNotFoundError:
        print(f"Error: The file '{image_path}' was not found.")
        return None
    except Exception as e:
        print(f"An error occurred during image pre-processing: {e}")
        return None

def process_student_card(image_path):
    processed_img = preprocess_image(image_path)
    
    if processed_img is None:
        return

    try:
        extracted_text = pytesseract.image_to_string(processed_img)
        
        if not extracted_text.strip():
            print("No text was detected in the processed image. Please ensure the image is clear.")
            return

        print("\n--- Extracted Raw Text ---")
        print(extracted_text)
        print("--------------------------\n")

        lines = extracted_text.split('\n')
        student_id = None
        student_name = None

        print("--- Searching for specific information ---")
        for line in lines:
            line = line.strip()
          
            if "ID" in line.upper() or "NUMBER" in line.upper():
                # A more robust split
                parts = line.split(':')
                if len(parts) > 1:
                    student_id = parts[-1].strip()
        
            elif "NAME" in line.upper():
                parts = line.split(':')
                if len(parts) > 1:
                    student_name = parts[-1].strip()
            
            if line.isdigit() and len(line) > 5:
                if student_id is None:
                    student_id = line
        
        print(f"Detected Student ID: {student_id}")
        print(f"Detected Student Name: {student_name}")
        print("----------------------------------------\n")

    except Exception as e:
        print(f"An error occurred during OCR: {e}")

if __name__ == "__main__":
    image_file = 'IMG_1160.jpeg'
    
    process_student_card(image_file)