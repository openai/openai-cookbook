# PornHubDownloader
A pornhub.com downloader that allows you to login, so you can download everything you have access to, including but not limited to private videos, 1080p or higher resolutions, premium videos and even paid videos that you own.

#### Supports the following things:

* Premium videos (untested, no access - yet - ETA: February)
* 1080p and higher resolution
* Private videos (untested - no access)
* Paid videos (untested - no access)

#### How does it work?

Download the program for your OS [here](https://github.com/RoyalFlyBy/PornHubDownloader/releases).

The program logs in on the account you supplied, then visits the link you supplied and downloads the video in the highest resolution available.

Logging in is optional however in order to enjoy the features that other downloaders seem to lack it is necessary.

Downloading too many videos too quickly will result in the failure of the script, you need to visit the url in such case and do the captcha before you can resume to download again.

#### Examples

Regular URL: https://www.pornhub.com/view_video.php?viewkey=ph6378a03c46eb5

Premium url: https://www.pornhubpremium.com/view_video.php?viewkey=ph5cc5d3bdc5b02

Downloading a single video

```./pornhubdownloader -video "https://www.pornhub.com/view_video.php?viewkey=ph6378a03c46eb5"```

This would result in a file called: ```OMG!! ð³ My STEP-SIS professional Onlyfans whore ð¥µ.mp4.mp4``` to be downloaded, the 720P version in this case.


You can also add a ```-namefmt``` flag to control the file name like this:

```./pornhubdownloader -video "https://www.pornhub.com/view_video.php?viewkey=ph6378a03c46eb5" -namefmt "[:VIDEO_VIEW_KEY :DATE_UPLOADED-:TIME_UPLOADED] :UPLOADER_NAME - :VIDEO_NAME" ```

This would affect the filename, now the file will be called ```[ph6378a03c46eb5 2022-11-19-10-28-40] Angel - OMG!! ð³ My STEP-SIS professional Onlyfans whore ð¥µ.mp4```

To speed things up you can also add ```-threads``` flag like this:

```./pornhubdownloader -video "https://www.pornhub.com/view_video.php?viewkey=ph6378a03c46eb5" -threads 3```

Alternatively you can save the links into a file in this fashion:

```
https://www.pornhub.com/view_video.php?viewkey=ph5ca48baebd5d7
https://www.pornhubpremium.com/view_video.php?viewkey=ph5cc5d3bdc5b02
https://www.pornhub.com/view_video.php?viewkey=ph5ca48baebd5d7
https://www.pornhubpremium.com/view_video.php?viewkey=ph5cc5d3bdc5b02
https://www.pornhub.com/view_video.php?viewkey=ph5ca48baebd5d7
https://www.pornhubpremium.com/view_video.php?viewkey=ph5cc5d3bdc5b02
https://www.pornhub.com/view_video.php?viewkey=ph5ca48baebd5d7
https://www.pornhubpremium.com/view_video.php?viewkey=ph5cc5d3bdc5b02
```

Save the file in the folder with the executable (or know the path to the file u just saved)

For this example let's say I saved it next to the executable with the name ```listofvids.txt```

Then now I can download all the videos using this command:

```./pornhubdownloader -videos=listofvids.txt```

As mentioned above you can add the other flags with this example to enjoy the other features.

You can log in by adding a `-username` and `-password` flag like this:

```./pornhubdownloader -videos=listofvids.txt -username "someusername" -password "somepassword"```

Alternatively, if you don't want to type in your username and or password each time u can set the `PHDL_USERNAME` `PHDL_PASSWORD` environment variables. Keep in mind the program will not always actually login since it actually keeps an active session after logging in.

#### For developers
You can access program-friendly downloader updates by adding a ```-daemon``` flag, this will cause the program to print JSON which you could parse and build a UI with.

## Disclaimer

Use at own risk.

#### My experience (outdated)
The downloader seems to be able to do 60+ videos of decent size without getting captchas but this was with a temporary premium account.

The program automatically crosses off the videos it managed to download from your list in case some fail you don't have to URL hunt

This is by far the most complete downloader around.

#### Future
I don't plan on actively working on this project, I will update when I have time in case bugs occur caused by pornhub updating their services.

Feel free to try to crack the .cookies file, if you succeed and can tell me how you did it it would be appreciated because I could always use tips on how to improve security.

If a feature is missing let me know.

If you think this program automatically does cool things, and you get mad it can only download the files that your account has access to, please gkys.
