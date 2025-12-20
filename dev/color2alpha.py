from PIL import Image
import numpy as np

def gimp_color_to_alpha_exact(image_path, target_color=(0, 0, 0), output_path=None):
    """
    Exact replication of GIMP's Color to Alpha algorithm

    Args:
        image_path: Path to input image
        target_color: RGB tuple of color to remove (default: black)
        output_path: Optional output path

    GIMP Settings replicated:
    - Transparency threshold: 0
    - Opacity threshold: 1
    - Mode: replace
    - Opacity: 100%
    """
    img = Image.open(image_path).convert("RGBA")
    data = np.array(img, dtype=np.float64)

    # Normalize to 0-1 range for calculations
    data = data / 255.0
    target = np.array(target_color, dtype=np.float64) / 255.0

    height, width = data.shape[:2]

    for y in range(height):
        for x in range(width):
            pixel = data[y, x]
            r, g, b, a = pixel[0], pixel[1], pixel[2], pixel[3]

            # GIMP's Color to Alpha algorithm
            tr, tg, tb = target[0], target[1], target[2]

            # Calculate the alpha based on how much of the target color is present
            if tr == 0.0 and tg == 0.0 and tb == 0.0:
                # Special case for pure black target
                # Alpha is the maximum of the RGB components
                new_alpha = max(r, g, b)

                if new_alpha > 0:
                    # Remove the black component, scale remaining color
                    data[y, x, 0] = r / new_alpha if new_alpha > 0 else 0
                    data[y, x, 1] = g / new_alpha if new_alpha > 0 else 0
                    data[y, x, 2] = b / new_alpha if new_alpha > 0 else 0
                else:
                    # Pure black becomes transparent
                    data[y, x, 0] = 0
                    data[y, x, 1] = 0
                    data[y, x, 2] = 0
                    new_alpha = 0

                # Replace mode: completely replace the alpha
                data[y, x, 3] = new_alpha * a

            else:
                # General case for non-black target colors
                # Calculate alpha as minimum ratio needed to remove target color
                alpha_r = (r - tr) / (1.0 - tr) if tr < 1.0 else 0
                alpha_g = (g - tg) / (1.0 - tg) if tg < 1.0 else 0
                alpha_b = (b - tb) / (1.0 - tb) if tb < 1.0 else 0

                new_alpha = max(0, max(alpha_r, alpha_g, alpha_b))

                if new_alpha > 0:
                    # Calculate new RGB values
                    data[y, x, 0] = (r - tr) / new_alpha + tr if new_alpha > 0 else tr
                    data[y, x, 1] = (g - tg) / new_alpha + tg if new_alpha > 0 else tg
                    data[y, x, 2] = (b - tb) / new_alpha + tb if new_alpha > 0 else tb
                else:
                    data[y, x, 0] = tr
                    data[y, x, 1] = tg
                    data[y, x, 2] = tb

                # Replace mode: completely replace the alpha
                data[y, x, 3] = new_alpha * a

    # Convert back to 0-255 range and uint8
    data = np.clip(data * 255.0, 0, 255).astype(np.uint8)
    result = Image.fromarray(data)

    if output_path:
        result.save(output_path)
    return result


def gimp_color_to_alpha_vectorized(image_path, target_color=(0, 0, 0), output_path=None):
    """
    Vectorized version of GIMP's Color to Alpha algorithm for better performance
    """
    img = Image.open(image_path).convert("RGBA")
    data = np.array(img, dtype=np.float64) / 255.0

    target = np.array(target_color, dtype=np.float64) / 255.0
    tr, tg, tb = target[0], target[1], target[2]

    r, g, b, a = data[:,:,0], data[:,:,1], data[:,:,2], data[:,:,3]

    if tr == 0.0 and tg == 0.0 and tb == 0.0:
        # Special case for black target - vectorized
        new_alpha = np.maximum(np.maximum(r, g), b)

        # Avoid division by zero
        safe_alpha = np.where(new_alpha > 0, new_alpha, 1)

        # Scale RGB values
        new_r = np.where(new_alpha > 0, r / safe_alpha, 0)
        new_g = np.where(new_alpha > 0, g / safe_alpha, 0)
        new_b = np.where(new_alpha > 0, b / safe_alpha, 0)

        # Apply new values
        data[:,:,0] = new_r
        data[:,:,1] = new_g
        data[:,:,2] = new_b
        data[:,:,3] = new_alpha * a

    else:
        # General case for non-black colors - vectorized
        alpha_r = np.where(tr < 1.0, (r - tr) / (1.0 - tr), 0)
        alpha_g = np.where(tg < 1.0, (g - tg) / (1.0 - tg), 0)
        alpha_b = np.where(tb < 1.0, (b - tb) / (1.0 - tb), 0)

        new_alpha = np.maximum(0, np.maximum(np.maximum(alpha_r, alpha_g), alpha_b))

        # Calculate new RGB
        safe_alpha = np.where(new_alpha > 0, new_alpha, 1)
        new_r = np.where(new_alpha > 0, (r - tr) / safe_alpha + tr, tr)
        new_g = np.where(new_alpha > 0, (g - tg) / safe_alpha + tg, tg)
        new_b = np.where(new_alpha > 0, (b - tb) / safe_alpha + tb, tb)

        data[:,:,0] = new_r
        data[:,:,1] = new_g
        data[:,:,2] = new_b
        data[:,:,3] = new_alpha * a

    # Convert back to uint8
    data = np.clip(data * 255.0, 0, 255).astype(np.uint8)
    result = Image.fromarray(data)

    if output_path:
        result.save(output_path)
    return result


# Usage examples
if __name__ == "__main__":
    # Basic usage - convert black to alpha

    #for i in range(13):
    gimp_color_to_alpha_exact("gradient_clear.png", output_path= "gradient_clear.png")

    print("Color to Alpha processing complete!")
