local settings_key = KEYS[1]
local job_weights_key = KEYS[2]
local job_expirations_key = KEYS[3]
local job_clients_key = KEYS[4]
local client_running_key = KEYS[5]
local client_num_queued_key = KEYS[6]
local client_last_registered_key = KEYS[7]
local client_last_seen_key = KEYS[8]

local now = tonumber(ARGV[1])
local client = ARGV[2]

local num_static_argv = 2
