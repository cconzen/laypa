#!/bin/bash

# Created by argbash-init v2.10.0
# ARG_OPTIONAL_SINGLE([GPU],[g],[Specify which GPU to run on],[all])
# ARG_POSITIONAL_SINGLE([input],[Input directory containing images])
# ARG_POSITIONAL_SINGLE([output],[Output directory with images and pagexml])
# ARG_DEFAULTS_POS([])
# ARG_HELP([<Script to run all steps of the baseline/region pipeline>])
# ARGBASH_GO()
# needed because of Argbash --> m4_ignore([
### START OF CODE GENERATED BY Argbash v2.10.0 one line above ###
# Argbash is a bash code generator used to get arguments parsing right.
# Argbash is FREE SOFTWARE, see https://argbash.io for more info


die()
{
	local _ret="${2:-1}"
	test "${_PRINT_HELP:-no}" = yes && print_help >&2
	echo "$1" >&2
	exit "${_ret}"
}


begins_with_short_option()
{
	local first_option all_short_options='gh'
	first_option="${1:0:1}"
	test "$all_short_options" = "${all_short_options/$first_option/}" && return 1 || return 0
}

# THE DEFAULTS INITIALIZATION - POSITIONALS
_positionals=()
_arg_input=
_arg_output=
# THE DEFAULTS INITIALIZATION - OPTIONALS
_arg_gpu="all"


print_help()
{
	printf '%s\n' "<The general help message of my script>"
	printf 'Usage: %s [-g|--GPU <arg>] [-h|--help] <input> <output>\n' "$0"
	printf '\t%s\n' "<input>: Input directory containing images"
	printf '\t%s\n' "<output>: Output directory with images and pagexml"
	printf '\t%s\n' "-g, --GPU: Specify which GPU to run on (default: 'all')"
	printf '\t%s\n' "-h, --help: Prints help"
}


parse_commandline()
{
	_positionals_count=0
	while test $# -gt 0
	do
		_key="$1"
		case "$_key" in
			-g|--GPU)
				test $# -lt 2 && die "Missing value for the optional argument '$_key'." 1
				_arg_gpu="$2"
				shift
				;;
			--GPU=*)
				_arg_gpu="${_key##--GPU=}"
				;;
			-g*)
				_arg_gpu="${_key##-g}"
				;;
			-h|--help)
				print_help
				exit 0
				;;
			-h*)
				print_help
				exit 0
				;;
			*)
				_last_positional="$1"
				_positionals+=("$_last_positional")
				_positionals_count=$((_positionals_count + 1))
				;;
		esac
		shift
	done
}


handle_passed_args_count()
{
	local _required_args_string="'input' and 'output'"
	test "${_positionals_count}" -ge 2 || _PRINT_HELP=yes die "FATAL ERROR: Not enough positional arguments - we require exactly 2 (namely: $_required_args_string), but got only ${_positionals_count}." 1
	test "${_positionals_count}" -le 2 || _PRINT_HELP=yes die "FATAL ERROR: There were spurious positional arguments --- we expect exactly 2 (namely: $_required_args_string), but got ${_positionals_count} (the last one was: '${_last_positional}')." 1
}


assign_positional_args()
{
	local _positional_name _shift_for=$1
	_positional_names="_arg_input _arg_output "

	shift "$_shift_for"
	for _positional_name in ${_positional_names}
	do
		test $# -gt 0 || break
		eval "$_positional_name=\${1}" || die "Error during argument parsing, possibly an Argbash bug." 1
		shift
	done
}

parse_commandline "$@"
handle_passed_args_count
assign_positional_args 1 "${_positionals[@]}"

# OTHER STUFF GENERATED BY Argbash

### END OF CODE GENERATED BY Argbash (sortof) ### ])
# [ <-- needed because of Argbash


if !(docker -v &> /dev/null); then
    echo "Docker is not installed please follow https://docs.docker.com/engine/install/"
    exit 1
fi

if !(docker image inspect docker.loghi-tooling:latest &> /dev/null); then
    echo "Loghi tooling is not installed please follow https://github.com/MMaas3/dockerize-images to install"
    exit 1
fi

if !(docker image inspect docker.laypa:latest &> /dev/null); then
    echo "Laypa is not installed please follow https://github.com/MMaas3/dockerize-images to install"
    exit 1
fi

tmpdir=$(mktemp -d)
input_dir=$_arg_input
output_dir=$_arg_output

# input_dir=/home/stefan/Documents/test
# output_dir=/home/stefan/Documents/test2

if [[ ! -d $input_dir ]]; then
    echo "Specified input dir (${input_dir}) does not exist, stopping program"
    exit 1
fi

if [[ ! -d $output_dir ]]; then
    echo "Could not find output dir (${output_dir}), creating one at specified location"
    mkdir -p $output_dir
fi

GPU=$_arg_gpu

DOCKERGPUPARAMS=""
if [[ $GPU -gt -1 ]]; then
        DOCKERGPUPARAMS="--gpus device=${GPU}"
        echo "using GPU ${GPU}"
fi

docker run $DOCKERGPUPARAMS --rm -it -m 32000m -v $input_dir:$input_dir -v $output_dir:$output_dir docker.laypa:latest \
    python run.py \
    -c configs/segmentation/pagexml_baseline_dataset_imagenet_freeze.yaml \
    -i $input_dir \
    -o $output_dir \
    -m baseline \
    --opts MODEL.WEIGHTS "" TEST.WEIGHTS pretrained_models/baseline_model_best_mIoU.pth
    # > /dev/null

if [[ $? -ne 0 ]]; then
    echo "Baseline detection has errored, stopping program"
    exit 1
fi

docker run $DOCKERGPUPARAMS --rm -it -m 32000m -v $input_dir:$input_dir -v $output_dir:$output_dir docker.laypa:latest \
    python run.py \
    -c configs/segmentation/pagexml_region_dataset_imagenet_freeze.yaml \
    -i $input_dir \
    -o $output_dir \
    -m region \
    --opts MODEL.WEIGHTS "" TEST.WEIGHTS pretrained_models/region_model_best_mIoU.pth
    # > /dev/null

if [[ $? -ne 0 ]]; then
    echo "Region detection has errored, stopping program"
    exit 1
fi

docker run --rm -v $output_dir:$output_dir docker.loghi-tooling /src/loghi-tooling/minions/target/appassembler/bin/MinionExtractBaselines \
    -input_path_png $output_dir/page/ \
    -input_path_page $output_dir/page/ \
    -output_path_page $output_dir/page/

if [[ $? -ne 0 ]]; then
    echo "Extract baselines has errored, stopping program"
    exit 1
fi

# ] <-- needed because of Argbash
