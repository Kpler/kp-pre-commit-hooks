# Set up the project with nix
let
  nixpkgs = builtins.fetchTarball {
    name   = "nixos-26.05-20260930";
    url    = "https://github.com/NixOS/nixpkgs/archive/78e9c786dc08.tar.gz";
    sha256 = "00v74sf1qzfx7553z60gsj7f2sbz95781h9scp4vxjalknhdmy2m";
  };

  pkgs = import nixpkgs { };

  python = pkgs.python314;
in
  pkgs.mkShell {
    buildInputs = [
      python
      pkgs.pre-commit
      pkgs.poetry
    ];
  }
