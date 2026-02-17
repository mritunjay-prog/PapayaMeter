import cv2
import configparser
import os

def get_config():
    config = configparser.ConfigParser()
    config_path = os.path.join(os.path.dirname(__file__), 'config.properties')
    if not os.path.exists(config_path):
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.properties')
    config.read(config_path)
    return config

class CameraHandler:
    def __init__(self, camera_side="left"):
        """
        camera_side: "left" or "right"
        """
        config = get_config()
        section = f"camera_{camera_side}"
        self.camera_side = camera_side
        self.device_path = config.get(section, 'device_path', fallback='/dev/video0' if camera_side == "left" else '/dev/video2')
        self.width = config.getint(section, 'frame_width', fallback=640)
        self.height = config.getint(section, 'frame_height', fallback=480)
        self.cap = None

    def start(self):
        # OpenCV can take a string path (like '/dev/video0') or an integer index
        self.cap = cv2.VideoCapture(self.device_path)
        if not self.cap.isOpened():
            print(f"❌ Camera Error ({self.camera_side}): Could not open device at {self.device_path}")
            return False
        
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        return True

    def get_frame(self):
        if self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                # Convert BGR (OpenCV) to RGB (Qt/standard)
                return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return None

    def stop(self):
        if self.cap:
            self.cap.release()
            self.cap = None

if __name__ == "__main__":
    # Test script for left camera by default
    import sys
    side = sys.argv[1] if len(sys.argv) > 1 else "left"
    cam = CameraHandler(side)
    if cam.start():
        print(f"{side.capitalize()} Camera started. Press 'q' in the window to quit.")
        while True:
            frame = cam.get_frame()
            if frame is not None:
                # Convert back to BGR for display in OpenCV window
                cv2.imshow(f'Camera Test - {side}', cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        cam.stop()
        cv2.destroyAllWindows()
