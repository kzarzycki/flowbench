Facts you know as the product owner. Reveal each ONLY if the agent directly asks
about it; never volunteer.

- Unknown flag key: if the agent asks what an evaluation should return for a flag
  key that does not exist, the answer is a 404 not-found response — NOT a silent
  `disabled=false`. A caller asking about a flag that isn't there is a bug on
  their side and should be told, not silently defaulted.
