{ pkgs }: {
  deps = [
    pkgs.chromium
    pkgs.chromedriver
    pkgs.python3
    pkgs.python3Packages.pip
    pkgs.python3Packages.virtualenv
  ];
}
