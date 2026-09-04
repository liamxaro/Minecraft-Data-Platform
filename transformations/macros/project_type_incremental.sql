{# ================================================================= #}
{# TYPE INFERENCE                                                     #}
{# ================================================================= #}


{% macro json_structure_to_duckdb_type(
    structure,
    column_name
) %}

    {#
        JSON knows that timestamps are strings, not that they are
        timestamps. Keep this one semantic override.

        Everything else is inferred from the actual JSON structure.
    #}

    {% if column_name == 'date_published' %}

        {{ return('TIMESTAMPTZ') }}

    {% endif %}


    {% if structure is string %}

        {% if structure == 'VARCHAR' %}

            {{ return('VARCHAR') }}

        {% elif structure in ['BIGINT', 'UBIGINT'] %}

            {{ return('BIGINT') }}

        {% elif structure == 'DOUBLE' %}

            {{ return('DOUBLE') }}

        {% elif structure == 'BOOLEAN' %}

            {{ return('BOOLEAN') }}

        {% elif structure == 'JSON' %}

            {{ return('JSON') }}

        {% elif structure == 'NULL' %}

            {#
                Don't create a column based exclusively on NULLs.
                If a later run contains actual values, it will be
                inferred then.
            #}

            {{ return(none) }}

        {% else %}

            {{ return('VARCHAR') }}

        {% endif %}

    {% endif %}


    {# ------------------------------------------------------------- #}
    {# ARRAYS                                                        #}
    {# ------------------------------------------------------------- #}

    {% if structure is sequence %}

        {% if structure | length == 1 %}

            {% set element_type = structure[0] %}

            {% if element_type is string %}

                {% if element_type == 'VARCHAR' %}

                    {{ return('VARCHAR[]') }}

                {% elif element_type in ['BIGINT', 'UBIGINT'] %}

                    {{ return('BIGINT[]') }}

                {% elif element_type == 'DOUBLE' %}

                    {{ return('DOUBLE[]') }}

                {% elif element_type == 'BOOLEAN' %}

                    {{ return('BOOLEAN[]') }}

                {% elif element_type == 'NULL' %}

                    {{ return(none) }}

                {% endif %}

            {% endif %}

        {% endif %}


        {#
            Arrays containing objects/structs are deliberately kept
            as JSON.

            Examples:
                dependencies
                files
        #}

        {{ return('JSON') }}

    {% endif %}


    {# ------------------------------------------------------------- #}
    {# OBJECTS                                                       #}
    {# ------------------------------------------------------------- #}

    {% if structure is mapping %}

        {{ return('JSON') }}

    {% endif %}


    {{ return('JSON') }}

{% endmacro %}



{# ================================================================= #}
{# INFER VERSION PAYLOAD SCHEMA FOR ONE BRONZE RUN                  #}
{# ================================================================= #}


{% macro infer_version_payload_columns(
    project_type,
    run_id
) %}

    {% set schema_query %}

        SELECT
            CAST(
                json_extract(
                    json_group_structure(
                        CAST(
                            payload AS JSON
                        )
                    ),
                    '$[0]'
                ) AS VARCHAR
            ) AS element_structure

        FROM bronze.main.modrinth_project_versions

        WHERE project_type = '{{ project_type }}'
            AND run_id = '{{ run_id }}'

    {% endset %}


    {% set schema_result = run_query(
        schema_query
    ) %}


    {% if schema_result is none %}

        {{ return([]) }}

    {% endif %}


    {% set structure_json =
        schema_result.columns[0].values()[0]
    %}


    {% if structure_json is none %}

        {{ return([]) }}

    {% endif %}


    {% set structure =
        fromjson(structure_json)
    %}


    {% if structure is not mapping %}

        {{
            exceptions.raise_compiler_error(
                "Expected Modrinth version payload "
                ~ "to contain JSON objects for "
                ~ project_type
                ~ " run_id="
                ~ run_id
                ~ ". Inferred structure: "
                ~ structure_json
            )
        }}

    {% endif %}


    {% set reserved_columns = [
        'id',
        'project_id',
        'run_id',
        'project_type',
        'version_id',
        'hashed_payload',
        'c_pull_timestamp_utc'
    ] %}


    {% set inferred_columns = [] %}


    {% for item in structure | dictsort %}

        {% set column_name = item[0] %}
        {% set column_structure = item[1] %}


        {% if column_name not in reserved_columns %}

            {% set data_type =
                json_structure_to_duckdb_type(
                    column_structure,
                    column_name
                )
            %}


            {% if data_type is not none %}

                {% do inferred_columns.append({
                    'name': column_name,
                    'data_type': data_type
                }) %}

            {% endif %}

        {% endif %}

    {% endfor %}


    {{ return(inferred_columns) }}

{% endmacro %}



{# ================================================================= #}
{# ADD NEWLY DISCOVERED SILVER COLUMNS                              #}
{# ================================================================= #}


{% macro evolve_version_target_schema(
    target_relation,
    inferred_columns
) %}

    {% set existing_columns =
        adapter.get_columns_in_relation(
            target_relation
        )
    %}


    {% set existing_names = [] %}


    {% for column in existing_columns %}

        {% do existing_names.append(
            column.name
        ) %}

    {% endfor %}


    {% for column in inferred_columns %}

        {% if column['name'] not in existing_names %}

            {{ log(
                "Adding inferred Silver column: "
                ~ column['name']
                ~ " "
                ~ column['data_type'],
                info=True
            ) }}


            {% set alter_sql %}

                ALTER TABLE {{ target_relation }}

                ADD COLUMN
                    {{ adapter.quote(column['name']) }}
                    {{ column['data_type'] }}

            {% endset %}


            {% do run_query(
                alter_sql
            ) %}


            {% do existing_names.append(
                column['name']
            ) %}

        {% endif %}

    {% endfor %}

{% endmacro %}



{# ================================================================= #}
{# GET DYNAMIC PAYLOAD COLUMNS FROM SILVER                           #}
{# ================================================================= #}


{% macro get_version_payload_columns(
    target_relation
) %}

    {% set metadata_columns = [
        'run_id',
        'project_type',
        'project_id',
        'version_id',
        'hashed_payload',
        'c_pull_timestamp_utc'
    ] %}


    {% set target_columns =
        adapter.get_columns_in_relation(
            target_relation
        )
    %}


    {% set payload_columns = [] %}


    {% for column in target_columns %}

        {% if column.name not in metadata_columns %}

            {% do payload_columns.append({
                'name': column.name,
                'data_type': column.data_type
            }) %}

        {% endif %}

    {% endfor %}


    {{ return(payload_columns) }}

{% endmacro %}



{# ================================================================= #}
{# DYNAMIC JSON EXTRACTION                                           #}
{# ================================================================= #}


{% macro render_version_payload_value(
    column_name,
    data_type
) %}

    {% set json_path =
        '$."' ~ column_name ~ '"'
    %}


    {% set normalized_type =
        data_type | upper
    %}


    {% if normalized_type in [
        'VARCHAR',
        'TEXT'
    ] %}

        json_extract_string(
            version_payload,
            '{{ json_path }}'
        )


    {% elif 'TIMESTAMP' in normalized_type %}

        CAST(
            json_extract_string(
                version_payload,
                '{{ json_path }}'
            )
            AS {{ data_type }}
        )


    {% elif normalized_type == 'JSON' %}

        json_extract(
            version_payload,
            '{{ json_path }}'
        )


    {% else %}

        CAST(
            json_extract(
                version_payload,
                '{{ json_path }}'
            )
            AS {{ data_type }}
        )

    {% endif %}

{% endmacro %}



{# ================================================================= #}
{# TRANSFORM ONE PROJECT TYPE + RUN                                  #}
{# ================================================================= #}


{% macro render_version_run(
    project_type,
    run_id,
    payload_columns
) %}


WITH exploded_versions AS (
    SELECT
        r.run_id,
        r.project_type,
        r.project_id,
        r.c_pull_timestamp_utc,

        UNNEST(
            json_extract(
                r.payload,
                '$[*]'
            )
        ) AS version_payload

    FROM bronze.main.modrinth_project_versions AS r

    WHERE r.project_type = '{{ project_type }}'
        AND r.run_id = '{{ run_id }}'
)


SELECT
    run_id,

    project_type,

    project_id,

    json_extract_string(
        version_payload,
        '$.id'
    ) AS version_id,

    sha256(
        CAST(
            version_payload AS VARCHAR
        )
    ) AS hashed_payload,

    c_pull_timestamp_utc

    {% for column in payload_columns %}

        ,

        {{
            render_version_payload_value(
                column['name'],
                column['data_type']
            )
        }} AS {{ adapter.quote(column['name']) }}

    {% endfor %}


FROM exploded_versions

WHERE json_extract_string(
    version_payload,
    '$.id'
) IS NOT NULL


{% endmacro %}



{# ================================================================= #}
{# CUSTOM MATERIALIZATION                                            #}
{# ================================================================= #}


{% materialization project_type_incremental, adapter='duckdb' %}

    {% set target_relation = this %}

    {% set existing_relation =
        load_relation(this)
    %}


    {% set project_types = [
        'shader',
        'datapack',
        'plugin',
        'minecraft_java_server',
        'resourcepack',
        'modpack',
        'mod'
    ] %}


    {% set rebuild_table =
        should_full_refresh()
        or existing_relation is none
    %}



    {# ============================================================= #}
    {# CREATE EMPTY SILVER TABLE                                     #}
    {# ============================================================= #}


    {% if rebuild_table %}

        {% if existing_relation is not none %}

            {% do adapter.drop_relation(
                existing_relation
            ) %}

        {% endif %}


        {% call statement(
            'create_target_table'
        ) %}

            CREATE TABLE {{ target_relation }} AS

            SELECT
                r.run_id,

                r.project_type,

                r.project_id,

                CAST(
                    NULL AS VARCHAR
                ) AS version_id,

                CAST(
                    NULL AS VARCHAR
                ) AS hashed_payload,

                r.c_pull_timestamp_utc

            FROM bronze.main.modrinth_project_versions AS r

            WHERE FALSE

        {% endcall %}

    {% endif %}



    {# ============================================================= #}
    {# PROCESS PROJECT TYPES                                         #}
    {# ============================================================= #}


    {% for project_type in project_types %}


        {{ log(
            "Processing project_type: "
            ~ project_type,
            info=True
        ) }}



        {# --------------------------------------------------------- #}
        {# DETERMINE WHICH SUCCESSFUL BRONZE RUNS NEED PROCESSING   #}
        {# --------------------------------------------------------- #}


        {% set run_query_sql %}

            SELECT
                r.run_id,

                MAX(
                    r.c_pull_timestamp_utc
                ) AS max_pull_timestamp

            FROM bronze.main.modrinth_project_versions AS r

            WHERE
                r.project_type = '{{ project_type }}'

                AND EXISTS (
                    SELECT
                        1

                    FROM bronze.main.ingestion_log AS l

                    WHERE l.run_id = r.run_id

                        AND l.project_type =
                            r.project_type

                        AND l.status =
                            'success'
                )


            {% if not rebuild_table %}

                AND r.c_pull_timestamp_utc > (
                    SELECT
                        COALESCE(
                            MAX(
                                c_pull_timestamp_utc
                            ),
                            TIMESTAMP '1900-01-01'
                        )

                    FROM {{ target_relation }}

                    WHERE
                        project_type =
                            '{{ project_type }}'
                )

            {% endif %}


            GROUP BY
                r.run_id

            ORDER BY
                max_pull_timestamp,
                r.run_id

        {% endset %}



        {% set run_results =
            run_query(
                run_query_sql
            )
        %}



        {# ========================================================= #}
        {# PROCESS RUNS SEQUENTIALLY                                 #}
        {# ========================================================= #}


        {% if run_results is not none %}

            {% for row in run_results.rows %}


                {% set run_id =
                    row[0]
                %}


                {{ log(
                    "Processing "
                    ~ project_type
                    ~ " run_id="
                    ~ run_id,
                    info=True
                ) }}



                {# ------------------------------------------------- #}
                {# INFER CURRENT API SCHEMA                         #}
                {# ------------------------------------------------- #}


                {% set inferred_columns =
                    infer_version_payload_columns(
                        project_type,
                        run_id
                    )
                %}



                {# ------------------------------------------------- #}
                {# EVOLVE SILVER IF NEW FIELDS APPEARED            #}
                {# ------------------------------------------------- #}


                {% do evolve_version_target_schema(
                    target_relation,
                    inferred_columns
                ) %}



                {# ------------------------------------------------- #}
                {# READ CURRENT SILVER SCHEMA                       #}
                {# ------------------------------------------------- #}


                {% set payload_columns =
                    get_version_payload_columns(
                        target_relation
                    )
                %}



                {# ------------------------------------------------- #}
                {# MERGE                                            #}
                {# ------------------------------------------------- #}


                {% call statement(
                    'merge_'
                    ~ project_type
                    ~ '_'
                    ~ loop.index
                ) %}


                    MERGE INTO
                        {{ target_relation }} AS dest


                    USING (

                        {{
                            render_version_run(
                                project_type,
                                run_id,
                                payload_columns
                            )
                        }}

                    ) AS src


                    ON
                        dest.project_type =
                            src.project_type

                        AND dest.project_id =
                            src.project_id

                        AND dest.version_id =
                            src.version_id



                    {# --------------------------------------------- #}
                    {# PAYLOAD CHANGED                              #}
                    {# --------------------------------------------- #}


                    WHEN MATCHED
                        AND (
                            src.hashed_payload
                            <> dest.hashed_payload
                        )

                    THEN UPDATE SET

                        run_id =
                            src.run_id,

                        hashed_payload =
                            src.hashed_payload,

                        c_pull_timestamp_utc =
                            src.c_pull_timestamp_utc

                        {% for column in payload_columns %}

                            ,

                            {{ adapter.quote(column['name']) }}
                                =
                            src.{{ adapter.quote(column['name']) }}

                        {% endfor %}



                    {# --------------------------------------------- #}
                    {# SAME PAYLOAD, NEWER OBSERVATION              #}
                    {# --------------------------------------------- #}


                    WHEN MATCHED
                        AND (
                            src.hashed_payload
                                = dest.hashed_payload

                            AND src.c_pull_timestamp_utc
                                > dest.c_pull_timestamp_utc
                        )

                    THEN UPDATE SET

                        run_id =
                            src.run_id,

                        c_pull_timestamp_utc =
                            src.c_pull_timestamp_utc



                    {# --------------------------------------------- #}
                    {# NEW VERSION                                  #}
                    {# --------------------------------------------- #}


                    WHEN NOT MATCHED

                    THEN INSERT (

                        run_id,

                        project_type,

                        project_id,

                        version_id,

                        hashed_payload,

                        c_pull_timestamp_utc

                        {% for column in payload_columns %}

                            ,

                            {{ adapter.quote(column['name']) }}

                        {% endfor %}

                    )


                    VALUES (

                        src.run_id,

                        src.project_type,

                        src.project_id,

                        src.version_id,

                        src.hashed_payload,

                        src.c_pull_timestamp_utc

                        {% for column in payload_columns %}

                            ,

                            src.{{ adapter.quote(column['name']) }}

                        {% endfor %}

                    )


                {% endcall %}


                {% do adapter.commit() %}


            {% endfor %}

        {% endif %}


    {% endfor %}



    {# ============================================================= #}
    {# DBT REQUIRES A MAIN STATEMENT                                 #}
    {# ============================================================= #}


    {% call statement('main') %}

        SELECT 1

    {% endcall %}


    {% do adapter.commit() %}


    {{
        return({
            'relations': [
                target_relation
            ]
        })
    }}


{% endmaterialization %}