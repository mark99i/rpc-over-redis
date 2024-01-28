cd ..

rm -r dist/
rm -r rpc_over_radis.egg-info/

py -m build
twine upload --verbose dist/*