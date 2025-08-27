# Remote Zip Browser

## About
Remote Zip Browser is a tool designed to explore and interact with ZIP archives hosted remotely. It allows users to browse, preview, and extract files from ZIP archives without downloading the entire archive. This is especially useful for large archives or when bandwidth is limited.

It all started when I had to download several files around 10 GB each. Since they didn’t contain what I expected, I had to delete them.
So, I began developing a minimal command-line utility for this purpose, until I discovered [remotezip](https://github.com/gtsystem/python-remotezip)
. Seeing that it had a well-developed background API, I decided to use that and focus my time on building a GUI.

Note: The app currently supports only ZIP files, and only static direct download links. (We do not support links that are webpages instead of direct downloads, nor dynamically generated ZIP streams such as GitHub’s “Download repository as ZIP.”)
I also have code for 7z support, but it is not well suited for a GUI yet. I plan to add 7z support within the next two years (due to school commitments).
## Showcase
lets take sample url
`https://mirror.kakao.com/eclipse/technology/epp/downloads/release/2025-06/R/eclipse-jee-2025-06-R-win32-x86_64.zip` (500+mb) and lets see speed
![here](https://i.vgy.me/rIcuSH.gif)

## Features
- Browse contents of remote ZIP files
- Preview files inside ZIP archives
- Selectively extract files without downloading the whole archive
- User-friendly interface

## Installation
You can download the latest release from the [Releases page](https://github.com/neptotech/Remote-zip-browser/releases/latest).

1. Download the installer for your platform from the link above.
2. Run the installer and follow the on-screen instructions.

## Usage
1. Launch the application.
2. Enter the URL of the remote ZIP file you want to browse.
3. Explore the contents and extract files as needed.

## License
This project is licensed under the terms of the LICENSE file provided in this repository.

## Contributing
Contributions are welcome! Please open issues or submit pull requests for improvements or bug fixes.

## Support
For questions or support, please open an issue on the [GitHub Issues page](https://github.com/neptotech/Remote-zip-browser/issues).
