# Useful commands 

Whether you need to debug, run a container or check on files, here we show the main command used. 

**In case of change in the codebase in the repository, run this to build the container and run the pipeline**
`docker compose build pipeline && docker compose run --rm pipeline`

**To copy the database validation report**: this has to be executed for each file. 
`2078  docker cp pbi-pipeline:/data/processed/reports/database_validation.html ./docs/reports`

**To create a bash session within a container**
`docker compose run --rm pipeline bash`

**Another copy command**. To copy the merged CSV for local analysis
`docker cp pbi-pipeline:/data/intermediate/csv/merged/. ./backup_old_merged/`
