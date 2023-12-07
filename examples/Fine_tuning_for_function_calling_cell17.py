function_list = [
    {
        "name": "takeoff_drone",
        "description": "Initiate the drone's takeoff sequence.",
        "parameters": {
            "type": "object",
            "properties": {
                "altitude": {
                    "type": "integer",
                    "description": "Specifies the altitude in meters to which the drone should ascend."
                }
            },
            "required": ["altitude"]
        }
    },
    {
        "name": "land_drone",
        "description": "Land the drone at its current location or a specified landing point.",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "enum": ["current", "home_base", "custom"],
                    "description": "Specifies the landing location for the drone."
                },
                "coordinates": {
                    "type": "object",
                    "description": "GPS coordinates for custom landing location. Required if location is 'custom'."
                }
            },
            "required": ["location"]
        }
    },
    {
        "name": "control_drone_movement",
        "description": "Direct the drone's movement in a specific direction.",
        "parameters": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": ["forward", "backward", "left", "right", "up", "down"],
                    "description": "Direction in which the drone should move."
                },
                "distance": {
                    "type": "integer",
                    "description": "Distance in meters the drone should travel in the specified direction."
                }
            },
            "required": ["direction", "distance"]
        }
    },
    {
        "name": "set_drone_speed",
        "description": "Adjust the speed of the drone.",
        "parameters": {
            "type": "object",
            "properties": {
                "speed": {
                    "type": "integer",
                    "description": "Specifies the speed in km/h."
                }
            },
            "required": ["speed"]
        }
    },
    {
        "name": "control_camera",
        "description": "Control the drone's camera to capture images or videos.",
        "parameters": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["photo", "video", "panorama"],
                    "description": "Camera mode to capture content."
                },
                "duration": {
                    "type": "integer",
                    "description": "Duration in seconds for video capture. Required if mode is 'video'."
                }
            },
            "required": ["mode"]
        }
    },
    {
        "name": "control_gimbal",
        "description": "Adjust the drone's gimbal for camera stabilization and direction.",
        "parameters": {
            "type": "object",
            "properties": {
                "tilt": {
                    "type": "integer",
                    "description": "Tilt angle for the gimbal in degrees."
                },
                "pan": {
                    "type": "integer",
                    "description": "Pan angle for the gimbal in degrees."
                }
            },
            "required": ["tilt", "pan"]
        }
    },
    {
        "name": "set_drone_lighting",
        "description": "Control the drone's lighting for visibility and signaling.",
        "parameters": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["on", "off", "blink", "sos"],
                    "description": "Lighting mode for the drone."
                }
            },
            "required": ["mode"]
        }
    },
    {
        "name": "return_to_home",
        "description": "Command the drone to return to its home or launch location.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "set_battery_saver_mode",
        "description": "Toggle battery saver mode.",
        "parameters": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["on", "off"],
                    "description": "Toggle battery saver mode."
                }
            },
            "required": ["status"]
        }
    },
    {
        "name": "set_obstacle_avoidance",
        "description": "Configure obstacle avoidance settings.",
        "parameters": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["on", "off"],
                    "description": "Toggle obstacle avoidance."
                }
            },
            "required": ["mode"]
        }
    },
    {
        "name": "set_follow_me_mode",
        "description": "Enable or disable 'follow me' mode.",
        "parameters": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["on", "off"],
                    "description": "Toggle 'follow me' mode."
                }
            },
            "required": ["status"]
        }
    },
    {
        "name": "calibrate_sensors",
        "description": "Initiate calibration sequence for drone's sensors.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "set_autopilot",
        "description": "Enable or disable autopilot mode.",
        "parameters": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["on", "off"],
                    "description": "Toggle autopilot mode."
                }
            },
            "required": ["status"]
        }
    },
    {
        "name": "configure_led_display",
        "description": "Configure the drone's LED display pattern and colors.",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "enum": ["solid", "blink", "pulse", "rainbow"],
                    "description": "Pattern for the LED display."
                },
                "color": {
                    "type": "string",
                    "enum": ["red", "blue", "green", "yellow", "white"],
                    "description": "Color for the LED display. Not required if pattern is 'rainbow'."
                }
            },
            "required": ["pattern"]
        }
    },
    {
        "name": "set_home_location",
        "description": "Set or change the home location for the drone.",
        "parameters": {
            "type": "object",
            "properties": {
                "coordinates": {
                    "type": "object",
                    "description": "GPS coordinates for the home location."
                }
            },
            "required": ["coordinates"]
        }
    },
    {
        "name": "reject_request",
        "description": "Use this function if the request is not possible.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
]
