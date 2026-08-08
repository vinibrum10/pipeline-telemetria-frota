CREATE OR REPLACE FUNCTION staging.safe_int(valor text)
RETURNS int
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
    RETURN valor::int;
EXCEPTION WHEN OTHERS THEN
    RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION staging.safe_numeric(valor text)
RETURNS numeric
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
    RETURN valor::numeric;
EXCEPTION WHEN OTHERS THEN
    RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION staging.safe_date(valor text)
RETURNS date
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
    RETURN valor::date;
EXCEPTION WHEN OTHERS THEN
    RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION staging.safe_timestamptz(valor text)
RETURNS timestamptz
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
    RETURN valor::timestamptz;
EXCEPTION WHEN OTHERS THEN
    RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION staging.safe_boolean(valor text)
RETURNS boolean
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
    RETURN valor::boolean;
EXCEPTION WHEN OTHERS THEN
    RETURN NULL;
END;
$$;