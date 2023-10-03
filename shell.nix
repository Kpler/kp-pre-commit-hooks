# Set up the project with nix
# cf https://github.com/Kpler/ct-webserver#option-2-using-nix
let
  nixpkgs = builtins.fetchTarball {
    name   = "nixos-23.05-20230814";
    url    = "https://github.com/NixOS/nixpkgs/archive/720e61ed8de1.tar.gz";
    sha256 = "0ii10wmm8hqdp7bii7iza58rjaqs4z3ivv71qyix3qawwxx48hw9";
  };

  pkgs = import nixpkgs { };
in
  pkgs.mkShell {
    buildInputs = [
      pkgs.pre-commit
    ];
  }
