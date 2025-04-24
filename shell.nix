# Set up the project with nix
# cf https://github.com/Kpler/ct-webserver#option-2-using-nix
let
  nixpkgs = builtins.fetchTarball {
    name   = "nixos-24.05-20240621";
    url    = "https://github.com/NixOS/nixpkgs/archive/dd457de7e08c.tar.gz";
    sha256 = "1kpamwmvs5xrmjgl3baxphmm69i0qydvgvk1n1c582ii4bdnzky0";
  };

  pkgs = import nixpkgs { };
in
  pkgs.mkShell {
    buildInputs = [
      pkgs.pre-commit
      pkgs.poetry
    ];
  }
