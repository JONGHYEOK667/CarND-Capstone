#!/usr/bin/env python
import rospy
from std_msgs.msg import Int32
from geometry_msgs.msg import PoseStamped, Pose
from styx_msgs.msg import TrafficLightArray, TrafficLight, Light
from styx_msgs.msg import Lane
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
from light_classification.tl_classifier import TLClassifier
import tf
import cv2
import yaml
import math

STATE_COUNT_THRESHOLD = 3

class TLDetector(object):
    def __init__(self):
        rospy.init_node('tl_detector')

        self.pose = None
        self.waypoints = None
        self.camera_image = None
        self.lights = []
        
        rospy.logwarn("TLDetector Node: {}".format(1))


        config_string = rospy.get_param("/traffic_light_config")
        self.config = yaml.load(config_string)
        model_path = self.config['tl']['model']

        self.light_classifier = TLClassifier(threshold=0.3, modelpath= model_path)

        sub1 = rospy.Subscriber('/current_pose', PoseStamped, self.pose_cb)
        sub2 = rospy.Subscriber('/base_waypoints', Lane, self.waypoints_cb)

        '''
        /vehicle/traffic_lights provides you with the location of the traffic light in 3D map space and
        helps you acquire an accurate ground truth data source for the traffic light
        classifier by sending the current color state of all traffic lights in the
        simulator. When testing on the vehicle, the color state will not be available. You'll need to
        rely on the position of the light and the camera image to predict it.
        '''
        sub3 = rospy.Subscriber('/vehicle/traffic_lights', TrafficLightArray, self.traffic_cb)
        sub6 = rospy.Subscriber('/image_color', Image, self.image_cb)

        self.upcoming_red_light_pub = rospy.Publisher('/traffic_waypoint', Light, queue_size=1)

        self.bridge = CvBridge()

        self.listener = tf.TransformListener()

        self.state = TrafficLight.UNKNOWN
        self.last_state = TrafficLight.UNKNOWN
        self.last_wp = -1
        self.state_count = 0

        rospy.spin()

    def pose_cb(self, msg):
        self.pose = msg

    def waypoints_cb(self, waypoints):
        self.waypoints = waypoints

    def traffic_cb(self, msg):
        self.lights = msg.lights

    def image_cb(self, msg):
        """Identifies red lights in the incoming camera image and publishes the index
            of the waypoint closest to the red light's stop line to /traffic_waypoint

        Args:
            msg (Image): image from car-mounted camera

        """
        self.has_image = True
        self.camera_image = msg
        light_wp, state = self.process_traffic_lights()

        '''
        Publish upcoming red lights at camera frequency.
        Each predicted state has to occur `STATE_COUNT_THRESHOLD` number
        of times till we start using it. Otherwise the previous stable state is
        used.
        '''
        if self.state != state:
            self.state_count = 0
            self.state = state
        elif self.state_count >= STATE_COUNT_THRESHOLD:
            self.last_state = self.state

            if state == TrafficLight.RED or state == TrafficLight.YELLOW:
                light_wp = light_wp
            #else:
            #    light_wp = -1

            self.last_wp = light_wp

            light_array = Light()
            light_array.state = Int32(self.state)
            light_array.waypoint = Int32(light_wp)

            rospy.logwarn("State: %d ... light waypoint: %d", self.state, light_wp)

            self.upcoming_red_light_pub.publish(light_array)
        else:
            light_array = Light()
            light_array.state = Int32(self.state)
            light_array.waypoint = Int32(light_wp)  #self.last_wp)

            rospy.logwarn("State: %d ... last light waypoint: %d", self.state, self.last_wp)

            self.upcoming_red_light_pub.publish(light_array)
        self.state_count += 1

    def get_closest_waypoint(self, pose):
        """Identifies the closest path waypoint to the given position
            https://en.wikipedia.org/wiki/Closest_pair_of_points_problem
        Args:
            pose (Pose): position to match a waypoint to

        Returns:
            int: index of the closest waypoint in self.waypoints

        """
        min_dist = float("inf")
        waypoint_index = -1

        pos_x, pos_y = pose.position.x, pose.position.y
        if self.waypoints is None:
            rospy.logwarn("[TL_DETECTOR] Waypoint is None!!!")
        else:
            for idx, wp in enumerate(self.waypoints.waypoints):
                wp_x = wp.pose.pose.position.x
                wp_y = wp.pose.pose.position.y
                dist = math.sqrt((wp_x - pos_x)**2 + (wp_y - pos_y)**2)
                if dist < min_dist:
                    waypoint_index = idx
                    min_dist = dist

        return waypoint_index

    def get_light_state(self, light):
        """Determines the current color of the traffic light

        Args:
            light (TrafficLight): light to classify

        Returns:
            int: ID of traffic light color (specified in styx_msgs/TrafficLight)

        """
        if(not self.has_image):
            self.prev_light_loc = None
            return False

        cv_image = self.bridge.imgmsg_to_cv2(self.camera_image, "bgr8")

        #Get classification
        return self.light_classifier.get_classification(cv_image)

    def process_traffic_lights(self):
        """Finds closest visible traffic light, if one exists, and determines its
            location and color

        Returns:
            int: index of waypoint closes to the upcoming stop line for a traffic light (-1 if none exists)
            int: ID of traffic light color (specified in styx_msgs/TrafficLight)

        """
        light = None
        light_wp = None
        traffic_light_distance = float("inf")

        stop_line_positions = self.config['stop_line_positions']
        if(self.pose):
            car_position = self.get_closest_waypoint(self.pose.pose)
        else:
            return -1, TrafficLight.UNKNOWN

        for current_stop_line_position in stop_line_positions:

            line_stop_pose = Pose()
            line_stop_pose.position.x = current_stop_line_position[0]
            line_stop_pose.position.y = current_stop_line_position[1]
            traffic_line_waypoint = self.get_closest_waypoint(line_stop_pose)

            if traffic_line_waypoint >= car_position :
                if light_wp is None:
                    light_wp = traffic_line_waypoint
                    light = line_stop_pose
                elif traffic_line_waypoint < light_wp:
                    light_wp = traffic_line_waypoint
                    light = line_stop_pose
        if light:
            state = self.get_light_state(light)

            rospy.loginfo("process_traffic_lights State: %d ... light waypoint: %d", state, light_wp)

            return light_wp, state

        return -1, TrafficLight.UNKNOWN

if __name__ == '__main__':
    try:
        TLDetector()
    except rospy.ROSInterruptException:
        rospy.logerr('Could not start traffic node.')
