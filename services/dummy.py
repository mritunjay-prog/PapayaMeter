import cv2
import numpy as np
import torch
from ultralytics import YOLO

# ==========================================
# CONFIGURATION - Adjust these for your device
# ==========================================
CONFIG = {
    # Video Source (0 for webcam, path for file, or rtsp:// string)
    "source": "/home/mritunjay/Downloads/park.mp4",
    
    # Model Path (.pt for dev, use .engine for Jetson TensorRT)
    "model_path": "yolo11n.pt",
    
    # Performance Tuning
    "resize_dim": (1024, 576),  # (Width, Height) - Smaller is faster
    "skip_frames": 5,           # Detect every Nth frame (higher = faster, lower = smoother)
    
    # Detection Settings
    "conf_threshold": 0.3,      # Minimum confidence for detection
    "classes": [2, 3, 5, 7],    # 2:car, 3:motorcycle, 5:bus, 7:truck
    
    # Device Optimization
    "device": "cuda" if torch.cuda.is_available() else "cpu"
}
# ==========================================

# Global variables
points = []
roi_defined = False
car_was_in_roi = False
detected_boxes = []

def draw_polygon(event, x, y, flags, param):
    global points, roi_defined
    if event == cv2.EVENT_LBUTTONDOWN and not roi_defined:
        points.append((x, y))

def main():
    global points, roi_defined, car_was_in_roi, detected_boxes
    
    # Initialize Video
    cap = cv2.VideoCapture(CONFIG["source"])
    if not cap.isOpened():
        print(f"Error: Could not open source {CONFIG['source']}")
        return

    # Get FPS for normal speed playback
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0: fps = 30 # Fallback
    frame_delay = int(1000 / fps)

    # Load Model onto specific device
    print(f"Loading model '{CONFIG['model_path']}' on '{CONFIG['device']}'...")
    model = YOLO(CONFIG["model_path"])
    model.to(CONFIG["device"])

    cv2.namedWindow('Parking Monitor')
    cv2.setMouseCallback('Parking Monitor', draw_polygon)

    frame_count = 0
    print(f"\nRunning with skip_frames={CONFIG['skip_frames']} and device={CONFIG['device']}")
    print("Controls: 'c' to Close ROI, 'r' to Reset, 'q' to Quit")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Resize for performance
        frame = cv2.resize(frame, CONFIG["resize_dim"])

        # Visualize drawing ROI
        for i in range(len(points)):
            cv2.circle(frame, points[i], 6, (0, 0, 255), -1) 
            if i > 0:
                cv2.line(frame, points[i-1], points[i], (255, 255, 0), 4)
        
        if roi_defined:
            polygon_array = np.array(points, np.int32)
            cv2.polylines(frame, [polygon_array], True, (0, 255, 0), 2)
            
            # AI Inference Path
            if frame_count % CONFIG["skip_frames"] == 0:
                results = model(
                    frame, 
                    verbose=False, 
                    classes=CONFIG["classes"], 
                    conf=CONFIG["conf_threshold"]
                )
                
                car_currently_in_roi = False
                detected_boxes = []
                
                # Check for CUDA/CPU compatibility and extract results
                for result in results:
                    boxes = result.boxes.cpu().numpy() # Move to CPU for CV2 drawing
                    for box in boxes:
                        x1, y1, x2, y2 = box.xyxy[0]
                        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                        
                        is_inside = cv2.pointPolygonTest(polygon_array, (cx, cy), False) >= 0
                        if is_inside: car_currently_in_roi = True
                        
                        detected_boxes.append({
                            'coords': (int(x1), int(y1), int(x2), int(y2)),
                            'center': (int(cx), int(cy)),
                            'inside': is_inside
                        })

                # Event Logging
                if car_currently_in_roi and not car_was_in_roi:
                    print("[ALERT] Vehicle entered the zone!")
                elif not car_currently_in_roi and car_was_in_roi:
                    print("[INFO] Zone cleared.")
                    
                car_was_in_roi = car_currently_in_roi

            # Draw saved boxes
            for box in detected_boxes:
                color = (0, 0, 255) if box['inside'] else (255, 0, 0)
                cv2.rectangle(frame, (box['coords'][0], box['coords'][1]), (box['coords'][2], box['coords'][3]), color, 2)
                if box['inside']:
                    cv2.circle(frame, box['center'], 4, (0, 255, 255), -1)

        frame_count += 1
        cv2.imshow('Parking Monitor', frame)

        key = cv2.waitKey(frame_delay) & 0xFF
        if key == ord('q'): break
        elif key == ord('r'):
            points = []; roi_defined = False; detected_boxes = []
        elif key == ord('c') and len(points) >= 3:
            roi_defined = True

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()