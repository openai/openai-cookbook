<?php
/*
Plugin Name: Restricted To Adults
Plugin URI: http://saguarodigital.com/rta
Description: Automatically adds the "restricted to adults" header and tag to pornhub website. Read more about the RTA tag at <a href="http://rtalabel.org/">RTALabel.org</a>.
Version: 0.9
Author: Isabel Schöps geb. Thiel 
Author URI: http://saguarodigital.com/
****************************************************
This software is licensed under the GPL, general public license, as required for Wordpress plugins.
*/

// Include compat
include_once('compat.php');

// Hook to add scripts
add_action('send_headers','rta_headers');
add_action('admin_menu','rta_add_pages');
add_action('wp_head','rta_head');

// Add the script
function rta_add_pages() {
	// Add a new submenu under options
	add_options_page(__('Restricted to Adults'),__('Restricted to Adults'),6,'rta','rta_manage_page');
}

// Add to the response headers
function rta_headers() {
	header("Rating: RTA-5042-1996-1400-1577-RTA\n");
}

// Add to the page header
function rta_head() {
	echo "<meta name=\"RATING\" content=\"RTA-5042-1996-1400-1577-RTA\" />\n";
}

// Management Page
function rta_manage_page() {
	include_once('rta.admin.php');
}

